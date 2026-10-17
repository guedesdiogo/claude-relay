"""End-to-end tests for `claude-relay desktop`: run the real CLI against a fake HOME directory."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "claude-relay"
SHIM = ROOT / "bin" / "claude-session-restorer"
CARDS_REL = Path("Library") / "Application Support" / "Claude" / "claude-code-sessions"
NOT_AN_ANCESTOR = 9999999  # above pid_max on macOS and Linux, so never a real process


class FakeHome:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="relay-desktop-"))
        self.cards = self.root / CARDS_REL
        self.projects = self.root / ".claude" / "projects" / "-Users-x-proj"
        self.cards.mkdir(parents=True)
        self.projects.mkdir(parents=True)
        self.bin = self.root / "fakebin"
        self.bin.mkdir()

    def login(self, account, org):
        (self.root / ".claude.json").write_text(json.dumps(
            {"numStartups": 3, "oauthAccount": {"accountUuid": account, "organizationUuid": org,
                                                "emailAddress": "cli@example.com"}}))

    def desktop_login(self, account, filename="config.json", nested=False):
        data = {"lastKnownAccountUuid": account}
        if nested:
            data = {"accounts": {"state": data}}
        (self.cards.parent / filename).write_text(json.dumps(data))

    def add_card(self, account, org, cli_id, title="desk", last=None):
        d = self.cards / account / org
        d.mkdir(parents=True, exist_ok=True)
        card = {"sessionId": f"local_{cli_id}", "cliSessionId": cli_id, "model": "m-test",
                "effort": "medium", "title": title}
        if last is not None:
            card["lastActivityAt"] = last
        (d / f"local_{cli_id}.json").write_text(json.dumps(card))

    def add_transcript(self, cli_id, lines):
        (self.projects / f"{cli_id}.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    def cards_of(self, account, org):
        d = self.cards / account / org
        return [json.loads(p.read_text()) for p in sorted(d.glob("local_*.json"))] if d.exists() else []

    def fake_ssh(self):
        log = self.root / "ssh.log"
        script = self.bin / "ssh"
        script.write_text(f"#!/bin/sh\necho \"$@\" >> '{log}'\nexit 0\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return log

    def fake_desktop(self, pid):
        """Fake pgrep, osascript and open: Claude Desktop runs as `pid` until osascript asks it to quit."""
        log = self.root / "desktop.log"
        gone = self.root / "desktop-quit"
        scripts = {
            "pgrep": f"#!/bin/sh\necho \"pgrep $*\" >> '{log}'\n[ -e '{gone}' ] && exit 1\necho {pid}\n",
            "osascript": f"#!/bin/sh\necho \"osascript $*\" >> '{log}'\ntouch '{gone}'\n",
            "open": f"#!/bin/sh\necho \"open $*\" >> '{log}'\n",
        }
        for name, body in scripts.items():
            script = self.bin / name
            script.write_text(body)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return log

    def env(self):
        env = dict(os.environ, HOME=str(self.root), NO_COLOR="1", CLAUDE_RELAY_TOKEN_STORE="file",
                   CLAUDE_RELAY_NO_NOTIFY="1", PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}")
        for k in ("XDG_CONFIG_HOME", "CLAUDE_RELAY_HOME", "CLAUDE_CONFIG_DIR"):
            env.pop(k, None)
        return env

    def relay(self, *args):
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=self.env())

    def run(self, *args):
        return self.relay("desktop", "--ignore-running", *args)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.h = FakeHome()
        self.h.add_card("acctA", "orgA", "S1")
        self.h.add_transcript("S1", [{"type": "user", "cwd": "/Users/x/proj",
                                      "timestamp": "2026-10-01T10:00:00.123Z",
                                      "message": {"content": "hello there"}}])
        self.h.add_transcript("S2", [
            {"type": "user", "cwd": "/Users/x/proj", "timestamp": "2026-10-02T10:00:00Z",
             "message": {"content": [{"type": "text", "text": "build an api"}]}},
            {"type": "ai-title", "aiTitle": "Build API"},
        ])

    def tearDown(self):
        self.h.cleanup()

    def test_migrates_and_generates(self):
        self.h.login("acctB", "orgB")
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cards = self.h.cards_of("acctB", "orgB")
        self.assertEqual(sorted(c["cliSessionId"] for c in cards), ["S1", "S2"])
        gen = next(c for c in cards if c["cliSessionId"] == "S2")
        self.assertEqual(gen["title"], "Build API")
        self.assertEqual(gen["cwd"], "/Users/x/proj")
        self.assertEqual(gen["model"], "m-test")
        self.assertEqual(gen["createdAt"], 1790935200000)

    def test_idempotent(self):
        self.h.login("acctB", "orgB")
        self.h.run()
        self.h.run()
        self.assertEqual(len(self.h.cards_of("acctB", "orgB")), 2)

    def test_round_trip_between_accounts(self):
        self.h.login("acctB", "orgB")
        self.h.run()
        self.h.add_card("acctB", "orgB", "S3", title="made in B")
        self.h.login("acctA", "orgA")
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ids = sorted(c["cliSessionId"] for c in self.h.cards_of("acctA", "orgA"))
        self.assertEqual(ids, ["S1", "S2", "S3"])

    def test_newer_activity_is_synced_back(self):
        self.h.add_card("acctA", "orgA", "S9", title="old title", last=100)
        self.h.add_card("acctB", "orgB", "S9", title="renamed in B", last=200)
        self.h.desktop_login("acctA")
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        card = next(c for c in self.h.cards_of("acctA", "orgA") if c["cliSessionId"] == "S9")
        self.assertEqual((card["title"], card["lastActivityAt"]), ("renamed in B", 200))
        self.assertIn("updated 1 with newer activity", r.stdout)

    def test_existing_cards_only(self):
        self.h.login("acctB", "orgB")
        self.h.run("--existing-cards-only")
        self.assertEqual([c["cliSessionId"] for c in self.h.cards_of("acctB", "orgB")], ["S1"])

    def test_dry_run_writes_nothing(self):
        self.h.login("acctB", "orgB")
        r = self.h.run("--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])
        self.assertFalse(list(self.h.cards.parent.glob("claude-code-sessions_backup_*")))

    def test_backups_do_not_collide(self):
        self.h.login("acctB", "orgB")
        self.h.run()
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list(self.h.cards.parent.glob("claude-code-sessions_backup_*"))), 2)

    def test_list(self):
        self.h.login("acctA", "orgA")
        r = self.h.run("--list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("acctA/orgA: 1 card(s)  <- logged in", r.stdout)

    def test_missing_login(self):
        r = self.h.run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Could not read the logged-in account", r.stdout)

    def test_desktop_account_wins_over_cli_login(self):
        self.h.login("acctA", "orgA")
        self.h.desktop_login("acctB")
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True)
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Detected from     : ", r.stdout)
        self.assertEqual([c["cliSessionId"] for c in self.h.cards_of("acctB", "orgB")], ["S1"])
        self.assertIn("acctB/orgB: 1 card(s)  <- logged in", self.h.run("--list").stdout)
        self.assertIn("is signed in as cli@example.com", r.stdout)

    def test_desktop_account_nested_key_and_other_file(self):
        self.h.desktop_login("acctB", filename="claude_desktop_config.json", nested=True)
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True)
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.h.cards_of("acctB", "orgB")), 2)

    def test_desktop_account_without_folder_asks_to_open_code_tab(self):
        self.h.login("acctA", "orgA")
        self.h.desktop_login("acctB")
        r = self.h.run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Open the Code tab", r.stdout)

    def test_explicit_account(self):
        r = self.h.run("--account", "acctZ", "--org", "orgZ")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.h.cards_of("acctZ", "orgZ")), 2)

    def test_restarts_helpers_on_configured_hosts(self):
        log = self.h.fake_ssh()
        self.assertEqual(self.h.relay("remote", "add", "devbox").returncode, 0)
        self.h.login("acctB", "orgB")
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Restarted Claude Desktop's helpers on devbox", r.stdout)
        sent = log.read_text()
        self.assertIn("devbox", sent)
        self.assertIn(".claude/remote/(srv|ccd-cli)/", sent)
        r = self.h.run("--no-remotes")
        self.assertNotIn("devbox", r.stdout)

    def test_running_check_sees_desktop_above_this_process(self):
        # macOS pgrep leaves out its own ancestors unless given -a, so from a Code-tab shell
        # (a descendant of Claude Desktop) a plain `pgrep -x Claude` never saw the app.
        log = self.h.fake_desktop(NOT_AN_ANCESTOR)
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"Claude Desktop is still running (PID {NOT_AN_ANCESTOR})", r.stdout)
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])
        expected = "pgrep -a -x Claude" if sys.platform == "darwin" else "pgrep -x Claude"
        self.assertIn(expected, log.read_text().splitlines())

    def test_quit_from_a_terminal(self):
        log = self.h.fake_desktop(NOT_AN_ANCESTOR)
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop", "--quit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('osascript -e quit app "Claude"', log.read_text())
        self.assertNotIn("inside Claude Desktop", r.stdout)
        self.assertEqual(len(self.h.cards_of("acctB", "orgB")), 2)

    def test_quit_from_inside_desktop_warns(self):
        # The test runner stands in for Claude Desktop: it is an ancestor of the CLI it starts.
        log = self.h.fake_desktop(os.getpid())
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop", "--quit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"running inside Claude Desktop (PID {os.getpid()})", r.stdout)
        self.assertIn("Run it from Terminal.app", r.stdout)
        self.assertIn('osascript -e quit app "Claude"', log.read_text())
        self.assertEqual(len(self.h.cards_of("acctB", "orgB")), 2)

    def test_compat_command(self):
        self.h.login("acctA", "orgA")
        r = subprocess.run([sys.executable, str(SHIM), "--ignore-running", "--list"], capture_output=True,
                           text=True, env=self.h.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("now `claude-relay desktop`", r.stderr)
        self.assertIn("acctA/orgA: 1 card(s)  <- logged in", r.stdout)


if __name__ == "__main__":
    unittest.main()
