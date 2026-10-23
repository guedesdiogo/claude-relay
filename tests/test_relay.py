"""Tests for accounts, settings and automatic failover (`claude-relay run`) with a fake `claude`."""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "claude-relay"
FAKE = Path(__file__).resolve().parent / "fake_claude.py"
CONTINUE = "Continue exactly where you left off."


def load_module():
    loader = importlib.machinery.SourceFileLoader("claude_relay", str(CLI))
    spec = importlib.util.spec_from_loader("claude_relay", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


relay = load_module()


class Env:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="relay-run-"))
        self.log = self.root / "fake.log"
        self.log.write_text("")
        self.home_cfg = self.root / ".config" / "claude-relay"

    def env(self, **extra):
        env = dict(os.environ, HOME=str(self.root), NO_COLOR="1", CLAUDE_RELAY_TOKEN_STORE="file",
                   CLAUDE_RELAY_NO_NOTIFY="1", CLAUDE_RELAY_CLAUDE_BIN=str(FAKE), FAKE_LOG=str(self.log),
                   FAKE_WAIT="20")
        for k in ("XDG_CONFIG_HOME", "CLAUDE_RELAY_HOME", "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY",
                  "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)
        env.update(extra)
        return env

    def relay(self, *args, stdin=None, timeout=90, **extra):
        return subprocess.run([sys.executable, str(CLI), *args], input=stdin, capture_output=True, text=True,
                              env=self.env(**extra), timeout=timeout)

    def add(self, name, token):
        r = self.relay("accounts", "add", name, stdin=token + "\n")
        assert r.returncode == 0, r.stdout + r.stderr

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines() if '"argv"' in l]

    def statuslines(self):
        return [json.loads(l)["statusline"] for l in self.log.read_text().splitlines() if '"statusline"' in l]

    def state(self):
        return json.loads((self.home_cfg / "state.json").read_text())

    def write_state(self, data):
        self.home_cfg.mkdir(parents=True, exist_ok=True)
        (self.home_cfg / "state.json").write_text(json.dumps(data))

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


TOKEN_A = "sk-ant-oat01-" + "a" * 95  # 108 characters, like a token from `claude setup-token`
TOKEN_B = "sk-ant-oat01-" + "b" * 95
SPLIT = "sk-ant-oat01-" + "Ab3_" * 23 + "x-y"  # 108 characters, pasted from a narrow terminal below
SPLIT_LINES = [SPLIT[:51], SPLIT[51:73], SPLIT[73:]]  # the pieces seen on the Mac: 51 and 73 characters


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    def test_add_list_use_remove(self):
        self.e.add("work", TOKEN_A)
        r = self.e.relay("accounts", "add", "home", stdin=f"export CLAUDE_CODE_OAUTH_TOKEN={TOKEN_B}\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        token_file = self.e.home_cfg / "tokens" / "home"
        self.assertEqual(token_file.read_text().strip(), TOKEN_B)
        self.assertEqual(oct(token_file.stat().st_mode & 0o777), "0o600")
        out = self.e.relay("accounts", "list").stdout
        self.assertIn("* work", out)
        self.assertIn("  home", out)
        self.e.relay("use", "home")
        self.assertIn("* home", self.e.relay("status").stdout)
        self.e.relay("accounts", "remove", "home")
        self.assertFalse(token_file.exists())
        self.assertNotIn("home", self.e.relay("accounts", "list").stdout)

    def saved_token(self, name):
        return (self.e.home_cfg / "tokens" / name).read_text().strip()

    def test_token_broken_over_lines_is_joined(self):
        a, b, c = SPLIT_LINES
        pasted = f"\n{a}\n  {b}  \n{c}\n\nStore this token securely.\n"
        r = self.e.relay("accounts", "add", "work", stdin=pasted)  # `pbpaste | claude-relay accounts add`
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.saved_token("work"), SPLIT)
        token_file = self.e.root / "home.token"
        token_file.write_text(f"{a}\n{b}\n{c}\n")
        r = self.e.relay("accounts", "add", "home", "--token-file", str(token_file))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.saved_token("home"), SPLIT)
        quoted = f"export CLAUDE_CODE_OAUTH_TOKEN='{SPLIT[:60]}\n{SPLIT[60:]}'\n"
        self.assertEqual(relay.parse_token_text(quoted), SPLIT)
        self.assertEqual(relay.parse_token_text(f"{SPLIT}\nStore this token securely.\n"), SPLIT)

    @unittest.skipUnless(hasattr(os, "fork"), "needs a pseudo-terminal")
    def test_hidden_prompt_reads_a_token_pasted_over_lines(self):
        import pty
        import select
        pid, master = pty.fork()
        if pid == 0:  # the child's stdin and /dev/tty are the pseudo-terminal, as in Terminal.app
            os.execve(sys.executable, [sys.executable, str(CLI), "accounts", "add", "work"], self.e.env())
        out, pasted, deadline = b"", False, time.time() + 30
        while time.time() < deadline:
            if not pasted and b"Token: " in out:
                os.write(master, ("\n".join(SPLIT_LINES) + "\n").encode())  # one paste, three lines
                pasted = True
            if not select.select([master], [], [], 1)[0]:
                continue
            try:
                data = os.read(master, 4096)
            except OSError:  # Linux: the child closed the terminal
                data = b""
            if not data:
                break
            out += data
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.WEXITSTATUS(status), 0, out)
        self.assertEqual(self.saved_token("work"), SPLIT)
        self.assertNotIn(SPLIT_LINES[1].encode(), out)  # not echoed

    def test_part_of_a_token_is_refused(self):
        for piece in (SPLIT_LINES[0], SPLIT[:73], "x" * 108):
            r = self.e.relay("accounts", "add", "work", stdin=piece + "\n")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("Paste the whole token", r.stderr)
        self.assertFalse((self.e.home_cfg / "tokens" / "work").exists())

    def test_rejects_garbage_token(self):
        r = self.e.relay("accounts", "add", "x", stdin="hello\n")
        self.assertNotEqual(r.returncode, 0)

    def test_config_threshold(self):
        self.assertNotEqual(self.e.relay("config", "threshold", "0").returncode, 0)
        self.assertEqual(self.e.relay("config", "threshold", "90").returncode, 0)
        self.assertEqual(self.e.relay("config", "threshold").stdout.strip(), "90")

    def test_link_desktop_account(self):
        self.e.add("work", TOKEN_A)
        self.assertEqual(self.e.relay("accounts", "link", "work", "uuid-1").returncode, 0)
        self.assertEqual(self.e.relay("accounts", "link", "home", "uuid-2").returncode, 0)  # no token yet
        self.assertEqual(self.e.relay("accounts", "link", "home", "uuid-1").returncode, 0)  # moves the link
        cfg = json.loads((self.e.home_cfg / "config.json").read_text())
        links = {a["name"]: a.get("desktop_account") for a in cfg["accounts"]}
        self.assertEqual(links, {"work": None, "home": "uuid-1"})
        out = self.e.relay("accounts", "list").stdout
        self.assertIn("Desktop uuid-1", out)
        self.assertIn("[token missing]", out)

    def test_remote_list(self):
        self.e.relay("remote", "add", "devbox")
        self.e.relay("remote", "add", "other")
        self.e.relay("remote", "remove", "other")
        out = self.e.relay("remote", "list").stdout
        self.assertIn("devbox", out)
        self.assertNotIn("other", out)


class ArgTests(unittest.TestCase):
    def test_restart_args(self):
        argv = ["-c", "--model", "opus", "--add-dir", "a", "b", "-r", "sid", "--dangerously-skip-permissions",
                "fix the bug"]
        self.assertEqual(relay.restart_args(argv),
                         ["--model", "opus", "--add-dir", "a", "b", "--dangerously-skip-permissions"])
        self.assertEqual(relay.restart_args(["--resume=abc", "--permission-mode", "plan", "--", "hi"]),
                         ["--permission-mode", "plan"])
        self.assertEqual(relay.restart_args(["-p", "--output-format", "json", "summarise this"]),
                         ["-p", "--output-format", "json"])
        self.assertEqual(relay.restart_args(["-w", "feature-x", "--resume"]), ["-w", "feature-x"])
        self.assertEqual(relay.restart_args(["-w", "do the thing please"]), ["-w"])

    def test_user_settings_are_merged(self):
        argv, user = relay.split_settings_arg(
            ["--model", "x", "--settings", json.dumps({"model": "y", "statusLine": {"type": "command",
                                                                                    "command": "echo hi"},
                                                       "hooks": {"Stop": [{"hooks": [{"type": "command",
                                                                                      "command": "true"}]}]}})])
        self.assertEqual(argv, ["--model", "x"])
        merged = relay.relay_settings(user)
        self.assertEqual(merged["model"], "y")
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        self.assertIn("_statusline", merged["statusLine"]["command"])
        self.assertEqual(relay.find_user_statusline(user, "/nonexistent")["command"], "echo hi")

    def test_availability(self):
        now = time.time()
        state = {"usage": {"a": {"five_hour": {"used": 96, "resets_at": now + 100}}}, "exhausted": {}}
        self.assertIsNotNone(relay.account_block("a", state, 95, now))
        self.assertIsNone(relay.account_block("a", state, 100, now))
        state["usage"]["a"]["five_hour"]["resets_at"] = now - 1
        self.assertIsNone(relay.account_block("a", state, 95, now))
        state["exhausted"]["a"] = now + 50
        self.assertEqual(relay.account_block("a", state, 95, now)[0], "hit its limit")


class RunTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.e.add("a", TOKEN_A)
        self.e.add("b", TOKEN_B)

    def tearDown(self):
        self.e.cleanup()

    def test_plain_run_passes_args_and_token(self):
        r = self.e.relay("run", "--model", "opus", "hello", FAKE_SCENARIO="exit", ANTHROPIC_API_KEY="sk-key")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["argv"], ["--model", "opus", "hello"])
        self.assertEqual(calls[0]["token"], TOKEN_A)
        self.assertIsNone(calls[0]["api_key"])
        self.assertIn("⇄ a", self.e.statuslines()[0])
        self.assertIn("ignoring ANTHROPIC_API_KEY", r.stderr)

    def test_switches_after_turn_at_threshold(self):
        r = self.e.relay("run", "--model", "opus", "fix the bug", FAKE_SCENARIO="threshold")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual([c["account"] for c in calls], ["a", "b"])
        self.assertEqual(calls[1]["token"], TOKEN_B)
        self.assertEqual(calls[1]["argv"], ["--model", "opus", "--resume", "sess-1"])  # no prompt: turn ended
        self.assertIn("switching after this turn", self.e.statuslines()[0])
        self.assertEqual(self.e.state()["usage"]["a"]["five_hour"]["used"], 96)
        self.assertEqual(self.e.state()["active"], "b")
        self.assertIn("switching to 'b'", r.stderr)

    def test_starts_on_the_claude_desktop_account(self):
        published = {"active": "a", "usage": {}, "exhausted": {}, "desktop": "b", "desktop_at": time.time()}
        self.e.write_state(published)
        r = self.e.relay("run", FAKE_SCENARIO="exit")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.e.calls()[0]["account"], "b")
        self.assertIn("run` follows Claude Desktop's account (b)", self.e.relay("use", "a").stdout)
        for state, cfg in ((dict(published, desktop_at=time.time() - 3600), None),  # watch stopped
                           (published, "false")):
            if cfg:
                self.e.relay("config", "follow_desktop", cfg)
            self.e.write_state(state)
            self.e.log.write_text("")
            self.e.relay("run", FAKE_SCENARIO="exit")
            self.assertEqual(self.e.calls()[0]["account"], "a")

    def test_switches_after_turn_when_claude_desktop_switches(self):
        r = self.e.relay("run", "fix the bug", FAKE_SCENARIO="desktop-switch")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual([c["account"] for c in calls], ["a", "b"])
        self.assertEqual(calls[1]["argv"], ["--resume", "sess-1"])  # no prompt: the turn had ended
        self.assertIn("'a' is not the account Claude Desktop uses; switching to 'b'", r.stderr)

    def test_does_not_follow_an_exhausted_desktop_account(self):
        future = time.time() + 3600
        self.e.write_state({"active": "a", "usage": {}, "desktop": "b", "desktop_at": time.time(),
                            "exhausted": {"b": {"until": future, "reason": "hit its weekly limit"}}})
        r = self.e.relay("run", FAKE_SCENARIO="desktop-switch", FAKE_WAIT="3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["account"] for c in self.e.calls()], ["a"])

    def test_switches_and_continues_on_limit(self):
        started = time.time()
        r = self.e.relay("run", "fix the bug", FAKE_SCENARIO="limit")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual([c["account"] for c in calls], ["a", "b"])
        self.assertEqual(calls[1]["argv"], ["--resume", "sess-1", CONTINUE])
        mark = self.e.state()["exhausted"]["a"]
        self.assertGreater(mark["until"], time.time())
        self.assertEqual(mark["reason"], "hit its usage limit")
        self.assertGreater(mark["since"], started)  # so a clear made before the run does not drop it

    def test_switches_after_turn_when_marked_exhausted_elsewhere(self):
        r = self.e.relay("run", "fix the bug", FAKE_SCENARIO="marked-elsewhere")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual([c["account"] for c in calls], ["a", "b"])
        self.assertEqual(calls[1]["argv"], ["--resume", "sess-1"])  # no prompt: the turn had ended
        self.assertIn("'a' hit its weekly limit; switching to 'b'", r.stderr)

    def test_threshold_100_waits_for_the_limit(self):
        self.e.relay("config", "threshold", "100")
        r = self.e.relay("run", FAKE_SCENARIO="threshold", FAKE_WAIT="2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.e.calls()), 1)

    def test_temporary_capacity_error_does_not_switch(self):
        r = self.e.relay("run", FAKE_SCENARIO="capacity")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.e.calls()), 1)
        self.assertEqual(self.e.state()["exhausted"], {})

    def test_rejected_token_switches_account(self):
        r = self.e.relay("run", FAKE_SCENARIO="auth")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["account"] for c in self.e.calls()], ["a", "b"])
        self.assertIn("token rejected", r.stderr)
        self.assertIn("token rejected", self.e.relay("status").stdout)

    def test_print_mode_continues_on_other_account(self):
        r = self.e.relay("run", "-p", "--output-format", "json", "summarise", FAKE_SCENARIO="print-limit")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual(calls[1]["argv"], ["-p", "--output-format", "json", "--resume", "sess-1", CONTINUE])

    def test_print_mode_reads_error_from_transcript(self):
        r = self.e.relay("run", "-p", "summarise", FAKE_SCENARIO="print-limit-nohook")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.e.calls()
        self.assertEqual([c["account"] for c in calls], ["a", "b"])
        self.assertEqual(calls[1]["argv"], ["-p", "--resume", "sess-1", CONTINUE])
        self.assertIn("hit its usage limit", r.stderr)

    def test_no_account_available(self):
        future = time.time() + 3600
        self.e.write_state({"active": "a", "usage": {}, "exhausted": {"a": future, "b": future}})
        r = self.e.relay("run", FAKE_SCENARIO="exit")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.e.calls(), [])
        self.assertIn("no account is available", r.stderr)

    def test_single_account_keeps_running_when_limit_hit(self):
        self.e.relay("accounts", "remove", "b")
        r = self.e.relay("run", FAKE_SCENARIO="limit", FAKE_WAIT="3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.e.calls()), 1)

    def test_skips_account_over_threshold_at_start(self):
        future = time.time() + 3600
        self.e.write_state({"active": "a", "usage": {"a": {"seven_day": {"used": 99, "resets_at": future}}},
                            "exhausted": {}})
        r = self.e.relay("run", FAKE_SCENARIO="exit")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.e.calls()[0]["account"], "b")

    def test_user_statusline_is_kept(self):
        settings = self.e.root / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"statusLine": {"type": "command", "command": "echo MY-LINE"}}))
        self.e.relay("run", FAKE_SCENARIO="exit")
        line = self.e.statuslines()[0]
        self.assertTrue(line.startswith("MY-LINE"), line)
        self.assertIn("⇄ a", line)

    def plain(self, call):
        """Started as plain `claude`: no token, no claude-relay settings."""
        self.assertIsNone(call["token"])
        self.assertIsNone(call["account"])
        self.assertFalse(call["settings"])

    def test_subcommands_go_straight_to_claude(self):
        # `alias claude='claude-relay run'` must keep `claude setup-token`, `claude mcp list`... working.
        for argv in (["setup-token"], ["mcp", "list"], ["update"], ["--version"]):
            with self.subTest(argv=argv):
                self.e.log.write_text("")
                r = self.e.relay("run", *argv, FAKE_SCENARIO="exit")
                self.assertEqual(r.returncode, 0, r.stderr)
                calls = self.e.calls()
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["argv"], argv)
                self.plain(calls[0])

    def test_without_any_token_runs_plain_claude(self):
        e = Env()
        try:
            e.relay("accounts", "link", "a", "uuid-1")  # an account, but no token yet
            r = e.relay("run", "hello", FAKE_SCENARIO="exit")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(e.calls()[0]["argv"], ["hello"])
            self.plain(e.calls()[0])
            self.assertIn("no account has a token yet", r.stderr)
            self.assertIn("accounts add", r.stderr)
        finally:
            e.cleanup()

    def test_no_accounts(self):
        e = Env()
        try:
            r = e.relay("run", FAKE_SCENARIO="exit")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(e.calls()[0]["argv"], [])
            self.plain(e.calls()[0])
            self.assertIn("accounts add", r.stderr)
        finally:
            e.cleanup()


if __name__ == "__main__":
    unittest.main()
