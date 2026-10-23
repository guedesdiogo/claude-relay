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

    def add_card(self, account, org, cli_id, title="desk", last=None, **extra):
        d = self.cards / account / org
        d.mkdir(parents=True, exist_ok=True)
        card = dict({"sessionId": f"local_{cli_id}", "cliSessionId": cli_id, "model": "m-test",
                     "effort": "medium", "title": title}, **extra)
        if last is not None:
            card["lastActivityAt"] = last
        (d / f"{card['sessionId']}.json").write_text(json.dumps(card))
        return card

    def add_tasks(self, account, org, tasks, **extra):
        """Claude Desktop's per-account scheduled-tasks.json (format observed in October 2026)."""
        d = self.cards / account / org
        d.mkdir(parents=True, exist_ok=True)
        (d / "scheduled-tasks.json").write_text(json.dumps(dict({"scheduledTasks": tasks}, **extra)))

    def tasks_of(self, account, org):
        path = self.cards / account / org / "scheduled-tasks.json"
        return json.loads(path.read_text()) if path.exists() else None

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

    def fake_desktop(self, pid, after_quit=1):
        """Fake pgrep, osascript and open: Claude Desktop runs as `pid` until osascript asks it to quit.
        After that, pgrep exits with `after_quit` (1: no match)."""
        log = self.root / "desktop.log"
        gone = self.root / "desktop-quit"
        scripts = {
            "pgrep": f"#!/bin/sh\necho \"pgrep $*\" >> '{log}'\n[ -e '{gone}' ] && exit {after_quit}\necho {pid}\n",
            "osascript": f"#!/bin/sh\necho \"osascript $*\" >> '{log}'\ntouch '{gone}'\n",
            "open": f"#!/bin/sh\necho \"open $*\" >> '{log}'\n",
        }
        for name, body in scripts.items():
            script = self.bin / name
            script.write_text(body)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return log

    def break_pgrep(self, code):
        """Make the fake pgrep fail: it exits 2 on a syntax error and 3 on a fatal one (macOS and procps)."""
        script = self.bin / "pgrep"
        script.write_text(f"#!/bin/sh\necho \"pgrep $*\" >> '{self.root / 'desktop.log'}'\n"
                          f"echo 'pgrep: fake error' >&2\nexit {code}\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def env(self, path=None):
        env = dict(os.environ, HOME=str(self.root), NO_COLOR="1", CLAUDE_RELAY_TOKEN_STORE="file",
                   CLAUDE_RELAY_NO_NOTIFY="1",
                   PATH=path or f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}")
        for k in ("XDG_CONFIG_HOME", "CLAUDE_RELAY_HOME", "CLAUDE_CONFIG_DIR"):
            env.pop(k, None)
        return env

    def relay(self, *args, path=None):
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              env=self.env(path))

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

    def card(self, account, org, session_id):
        return next(c for c in self.h.cards_of(account, org) if c["sessionId"] == session_id)

    def test_newer_copy_replaces_the_card(self):
        # The session went on in B after it was archived in A: B's card is the one to keep, whole.
        self.h.add_card("acctA", "orgA", "S9", title="old title", last=100, completedTurns=4, prs=[],
                        error="usage limit", isArchived=True)
        newer = self.h.add_card("acctB", "orgB", "S9", title="renamed in B", last=200, completedTurns=9,
                                prs=[{"number": 7}], isArchived=False)
        self.h.desktop_login("acctA")
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.card("acctA", "orgA", "local_S9"), newer)
        self.assertEqual((self.h.cards / "acctA" / "orgA" / "local_S9.json").stat().st_mode & 0o777, 0o600)
        self.assertIn("Copied 0 card(s) from other accounts; updated 1 from a newer copy.", r.stdout)
        r = self.h.run("--existing-cards-only")
        self.assertIn("Copied 0 card(s) from other accounts.", r.stdout)

    def test_card_left_stale_by_older_versions_is_replaced(self):
        # Before 2.3.0 only lastActivityAt and the title were copied, so both copies can show the same
        # lastActivityAt; latestUserFrameAt still tells which one went on.
        self.h.add_card("acctA", "orgA", "S9", last=200, latestUserFrameAt=100, completedTurns=4)
        newer = self.h.add_card("acctB", "orgB", "S9", last=200, latestUserFrameAt=150, completedTurns=9)
        self.h.desktop_login("acctA")
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.card("acctA", "orgA", "local_S9"), newer)

    def test_archived_in_another_account_is_archived_here(self):
        # Archiving changes no timestamp, so both copies show the same activity.
        mine = self.h.add_card("acctA", "orgA", "S9", last=100, latestUserFrameAt=90, isArchived=False)
        self.h.add_card("acctB", "orgB", "S9", title="other title", last=100, latestUserFrameAt=90,
                        isArchived=True)
        self.h.desktop_login("acctA")
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.card("acctA", "orgA", "local_S9"), dict(mine, isArchived=True))
        self.assertIn("Copied 0 card(s) from other accounts; archived 1 archived in another account.",
                      r.stdout)
        r = self.h.run("--existing-cards-only")
        self.assertIn("Copied 0 card(s) from other accounts.", r.stdout)

    def test_newer_card_here_is_kept(self):
        # The session went on here after the other account archived or renamed its older copy.
        mine = self.h.add_card("acctA", "orgA", "S9", last=300, isArchived=False)
        self.h.add_card("acctB", "orgB", "S9", title="renamed in B", last=200, isArchived=True)
        self.h.desktop_login("acctA")
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.card("acctA", "orgA", "local_S9"), mine)
        self.assertIn("Copied 0 card(s) from other accounts.", r.stdout)

    def test_continuation_under_a_new_cli_session_replaces_the_card(self):
        # Claude Desktop can move a card to a new transcript; the card's sessionId stays the same.
        self.h.add_card("acctA", "orgA", "S9", sessionId="local_card", last=100)
        newer = self.h.add_card("acctB", "orgB", "S10", sessionId="local_card", last=200,
                                priorCliSessionIds=["S9"])
        for cli in ("S9", "S10"):
            self.h.add_transcript(cli, [{"type": "user", "cwd": "/Users/x/proj",
                                         "timestamp": "2026-10-03T10:00:00Z", "message": {"content": cli}}])
        self.h.desktop_login("acctA")
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cards = self.h.cards_of("acctA", "orgA")
        self.assertEqual(sorted(c["cliSessionId"] for c in cards), ["S1", "S10", "S2"])
        self.assertEqual(self.card("acctA", "orgA", "local_card"), newer)
        self.assertIn("updated 1 from a newer copy", r.stdout)

    def test_dry_run_counts_card_updates_without_writing(self):
        self.h.add_card("acctA", "orgA", "S8", last=100)
        self.h.add_card("acctB", "orgB", "S8", last=200)
        self.h.add_card("acctA", "orgA", "S9", last=100)
        self.h.add_card("acctB", "orgB", "S9", last=100, isArchived=True)
        before = self.h.cards_of("acctA", "orgA")
        self.h.desktop_login("acctA")
        r = self.h.run("--existing-cards-only", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Would copy 0 card(s) from other accounts; updated 1 from a newer copy; "
                      "archived 1 archived in another account.", r.stdout)
        self.assertEqual(self.h.cards_of("acctA", "orgA"), before)

    def test_recurring_scheduled_tasks_follow_the_account(self):
        daily = {"id": "daily", "displayName": "Daily", "cronExpression": "30 8 * * *", "enabled": True,
                 "filePath": "/Users/x/.claude/scheduled-tasks/daily/SKILL.md", "createdAt": 100,
                 "cwd": "/Users/x/Repos", "permissionMode": "auto", "permissionModeCarried": True,
                 "lastRunAt": "2026-10-17T11:39:41.471Z", "lastScheduledFor": "2026-10-17T11:30:00.000Z",
                 "notifySessionId": "local_abc"}
        self.h.add_tasks("acctA", "orgA", [
            daily,
            {"id": "shared", "cronExpression": "0 9 * * 1", "enabled": True, "filePath": "/a/SKILL.md"},
            {"id": "once", "fireAt": 1792000000000, "enabled": True, "filePath": "/o/SKILL.md"},
            {"id": "claude-relay-resume", "fireAt": 1792000000000, "enabled": True, "filePath": "/r/SKILL.md"},
        ], recordedSkips={"daily": ["from A"]})
        self.h.add_tasks("acctC", "orgC", [dict(daily, cwd="/Users/x/used-last")])
        older = self.h.cards / "acctA" / "orgA" / "scheduled-tasks.json"
        os.utime(older, (1000, 1000))
        mine = {"id": "shared", "cronExpression": "0 18 * * 5", "enabled": False, "filePath": "/b/SKILL.md"}
        self.h.add_tasks("acctB", "orgB", [mine], recordedSkips={}, sundayAliasBoundaryStamped=True)
        self.h.desktop_login("acctB")
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Copied 1 scheduled task(s) from other accounts.", r.stdout)
        data = self.h.tasks_of("acctB", "orgB")
        # The destination keeps its own tasks and fields; recurring tasks from other accounts are added
        # once each, without the bookkeeping of their last run there.
        self.assertEqual([t["id"] for t in data["scheduledTasks"]], ["shared", "daily"])
        self.assertEqual(data["scheduledTasks"][0], mine)
        copied = data["scheduledTasks"][1]
        for k in ("lastRunAt", "lastScheduledFor", "notifySessionId"):
            self.assertNotIn(k, copied)
        self.assertEqual(copied["cronExpression"], "30 8 * * *")
        self.assertEqual((copied["permissionMode"], copied["permissionModeCarried"]), ("auto", True))
        self.assertEqual(copied["cwd"], "/Users/x/used-last")  # the newest file wins
        self.assertEqual(data["recordedSkips"], {})
        self.assertIs(data["sundayAliasBoundaryStamped"], True)
        mode = (self.h.cards / "acctB" / "orgB" / "scheduled-tasks.json").stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)  # as Claude Desktop writes it
        # The sources are left as they were.
        self.assertEqual(len(self.h.tasks_of("acctA", "orgA")["scheduledTasks"]), 4)
        r = self.h.run("--existing-cards-only")
        self.assertIn("Copied 0 scheduled task(s) from other accounts.", r.stdout)
        self.assertEqual(len(self.h.tasks_of("acctB", "orgB")["scheduledTasks"]), 2)

    def test_scheduled_tasks_file_is_created_and_dry_run_only_counts(self):
        self.h.add_tasks("acctA", "orgA", [{"id": "daily", "cronExpression": "30 8 * * *", "enabled": True}])
        self.h.login("acctB", "orgB")
        r = self.h.run("--dry-run")
        self.assertIn("Would copy 1 scheduled task(s) from other accounts.", r.stdout)
        self.assertIsNone(self.h.tasks_of("acctB", "orgB"))
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.h.tasks_of("acctB", "orgB"),
                         {"scheduledTasks": [{"id": "daily", "cronExpression": "30 8 * * *", "enabled": True}]})

    def test_unreadable_scheduled_tasks_file_is_left_alone(self):
        self.h.add_tasks("acctA", "orgA", [{"id": "daily", "cronExpression": "30 8 * * *", "enabled": True}])
        path = self.h.cards / "acctB" / "orgB" / "scheduled-tasks.json"
        path.parent.mkdir(parents=True)
        self.h.desktop_login("acctB")
        for content in ("{not json", '{"scheduledTasks": {"daily": {}}}'):
            with self.subTest(content=content):
                path.write_text(content)
                r = self.h.run("--existing-cards-only")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("Could not read", r.stdout)
                self.assertEqual(path.read_text(), content)

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
        self.h.add_tasks("acctA", "orgA", [{"id": "daily", "cronExpression": "30 8 * * *", "enabled": True}])
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"Claude Desktop is still running (PID {NOT_AN_ANCESTOR})", r.stdout)
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])
        self.assertIsNone(self.h.tasks_of("acctB", "orgB"))
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

    def test_running_check_fails_closed_when_pgrep_errors(self):
        self.h.fake_desktop(NOT_AN_ANCESTOR)
        self.h.login("acctB", "orgB")
        for code in (2, 3):
            with self.subTest(code=code):
                self.h.break_pgrep(code)
                r = self.h.relay("desktop")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("Could not check whether Claude Desktop is running "
                              f"(pgrep exited with code {code}: pgrep: fake error)", r.stdout)
                self.assertIn("run again with --ignore-running.", r.stdout)
                self.assertEqual(self.h.cards_of("acctB", "orgB"), [])
                self.assertFalse(list(self.h.cards.parent.glob("claude-code-sessions_backup_*")))

    def test_running_check_fails_closed_without_pgrep(self):
        self.h.fake_desktop(NOT_AN_ANCESTOR)
        (self.h.bin / "pgrep").unlink()
        self.h.login("acctB", "orgB")
        # Only fakebin: with no PATH at all, Python would fall back to /bin:/usr/bin and the real pgrep.
        r = self.h.relay("desktop", path=str(self.h.bin))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Could not check whether Claude Desktop is running (could not run pgrep", r.stdout)
        self.assertIn("run again with --ignore-running.", r.stdout)
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])

    def test_overrides_do_not_need_the_running_check(self):
        self.h.fake_desktop(NOT_AN_ANCESTOR)
        self.h.break_pgrep(2)
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dest = self.h.root / "dest"
        r = self.h.relay("desktop", "--dest-root", str(dest))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(list(dest.glob("local_*.json"))), 2)
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])
        r = self.h.relay("desktop", "--ignore-running")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.h.cards_of("acctB", "orgB")), 2)

    def test_quit_does_not_act_without_a_running_check(self):
        log = self.h.fake_desktop(NOT_AN_ANCESTOR)
        self.h.break_pgrep(2)
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop", "--quit", "--reopen")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Could not check whether Claude Desktop is running", r.stdout)
        self.assertIn("run again with --ignore-running instead of --quit.", r.stdout)
        self.assertNotIn("osascript", log.read_text())
        self.assertNotIn("open ", log.read_text())
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])

    def test_quit_is_not_confirmed_by_a_failed_check(self):
        # pgrep sees the app, osascript asks it to quit, then pgrep fails: that is not "it quit".
        log = self.h.fake_desktop(NOT_AN_ANCESTOR, after_quit=3)
        self.h.login("acctB", "orgB")
        r = self.h.relay("desktop", "--quit", "--reopen")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Could not check whether Claude Desktop is running (pgrep exited with code 3)",
                      r.stdout)
        self.assertIn('osascript -e quit app "Claude"', log.read_text())
        self.assertNotIn("open ", log.read_text())
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])

    def test_compat_command(self):
        self.h.login("acctA", "orgA")
        r = subprocess.run([sys.executable, str(SHIM), "--ignore-running", "--list"], capture_output=True,
                           text=True, env=self.h.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("now `claude-relay desktop`", r.stderr)
        self.assertIn("acctA/orgA: 1 card(s)  <- logged in", r.stdout)


if __name__ == "__main__":
    unittest.main()
