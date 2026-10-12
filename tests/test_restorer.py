"""End-to-end tests: run the real CLI against a fake HOME directory."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent / "bin" / "claude-session-restorer"
CARDS_REL = Path("Library") / "Application Support" / "Claude" / "claude-code-sessions"


class FakeHome:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="csr-test-"))
        self.cards = self.root / CARDS_REL
        self.projects = self.root / ".claude" / "projects" / "-Users-x-proj"
        self.cards.mkdir(parents=True)
        self.projects.mkdir(parents=True)

    def login(self, account, org):
        (self.root / ".claude.json").write_text(json.dumps(
            {"numStartups": 3, "oauthAccount": {"accountUuid": account, "organizationUuid": org,
                                                "emailAddress": "x@example.com"}}))

    def desktop_login(self, account, filename="config.json", nested=False):
        data = {"lastKnownAccountUuid": account}
        if nested:
            data = {"accounts": {"state": data}}
        (self.cards.parent / filename).write_text(json.dumps(data))

    def add_card(self, account, org, cli_id, title="desk"):
        d = self.cards / account / org
        d.mkdir(parents=True, exist_ok=True)
        (d / f"local_{cli_id}.json").write_text(json.dumps(
            {"sessionId": f"local_{cli_id}", "cliSessionId": cli_id, "model": "m-test",
             "effort": "medium", "title": title}))

    def add_transcript(self, cli_id, lines):
        (self.projects / f"{cli_id}.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    def cards_of(self, account, org):
        d = self.cards / account / org
        return [json.loads(p.read_text()) for p in sorted(d.glob("local_*.json"))] if d.exists() else []

    def run(self, *args):
        env = dict(os.environ, HOME=str(self.root), NO_COLOR="1")
        return subprocess.run([sys.executable, str(CLI), "--ignore-running", *args],
                              capture_output=True, text=True, env=env)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class RestorerTests(unittest.TestCase):
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
        self.assertEqual(gen["model"], "m-test")  # cloned from template card
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
        # Claude Desktop switched to B; ~/.claude.json still says A (what happened on a real Mac).
        self.h.login("acctA", "orgA")
        self.h.desktop_login("acctB")
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True)
        r = self.h.run("--existing-cards-only")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Detected from     : ", r.stdout)
        self.assertEqual([c["cliSessionId"] for c in self.h.cards_of("acctB", "orgB")], ["S1"])
        self.assertIn("acctB/orgB: 1 card(s)  <- logged in", self.h.run("--list").stdout)

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
        self.assertEqual(self.h.cards_of("acctA", "orgA")[0]["cliSessionId"], "S1")  # untouched

    def test_explicit_account(self):
        r = self.h.run("--account", "acctZ", "--org", "orgZ")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.h.cards_of("acctZ", "orgZ")), 2)


if __name__ == "__main__":
    unittest.main()
