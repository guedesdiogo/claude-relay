"""End-to-end tests for `claude-relay watch` and `service`: run the real CLI against fake HOME folders.

A fake `ssh` runs the remote command against a second fake HOME, standing in for an SSH host."""
import json
import os
import plistlib
import stat
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

from test_desktop import NOT_AN_ANCESTOR, FakeHome
from test_relay import CLI, load_module

relay = load_module()
WEEKLY = "You've hit your weekly limit · resets 5pm (America/Sao_Paulo)"
TOKEN_G = "sk-ant-oat01-" + "g" * 95


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(epoch))


def limit_entry(at, resets_at, entrypoint="claude-desktop", kind="seven_day"):
    """A failed turn as Claude Code 2.1.299 records it when the account hits its usage limit."""
    return {"type": "assistant", "uuid": str(uuid.uuid4()), "timestamp": iso(at), "entrypoint": entrypoint,
            "isApiErrorMessage": True, "error": "rate_limit", "apiError": "usage_limit_reached",
            "quotaLimits": {"status": "rejected", "resetsAt": resets_at, "rateLimitType": kind},
            "message": {"role": "assistant", "content": [{"type": "text", "text": WEEKLY}]}}


def capacity_entry(at):
    return {"type": "assistant", "uuid": str(uuid.uuid4()), "timestamp": iso(at), "entrypoint": "claude-desktop",
            "isApiErrorMessage": True, "error": "rate_limit",
            "message": {"content": [{"type": "text", "text": "Request rejected (429) · this may be a "
                                                             "temporary capacity issue"}]}}


def reply_entry(at):
    return {"type": "assistant", "uuid": str(uuid.uuid4()), "timestamp": iso(at), "entrypoint": "claude-desktop",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}}


def user_entry(at):
    return {"type": "user", "uuid": str(uuid.uuid4()), "timestamp": iso(at), "entrypoint": "claude-desktop",
            "cwd": "/Users/x/proj", "message": {"content": "keep going"}}


class WatchHome(FakeHome):
    def __init__(self):
        super().__init__()
        self.remote = self.root / "remote-home"
        self.remote_projects = self.remote / ".claude" / "projects" / "-home-x-proj"
        self.remote_projects.mkdir(parents=True)

    def transcript(self, cli_id, entries, age=600, remote=False):
        """Write a transcript last modified `age` seconds ago."""
        path = (self.remote_projects if remote else self.projects) / f"{cli_id}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in entries))
        t = time.time() - age
        os.utime(path, (t, t))
        return path

    def fake_remote_ssh(self):
        """ssh that runs the command against the fake remote HOME; `pkill` is only logged. A script in
        `during-ssh` runs once on this machine first, as if typed while `watch` waits on ssh."""
        log = self.root / "ssh.log"
        during = self.root / "during-ssh"
        script = self.bin / "ssh"
        script.write_text(
            "#!/bin/sh\n"
            "while [ $# -gt 0 ]; do case \"$1\" in -o) shift 2 ;; -*) shift ;; *) break ;; esac; done\n"
            "host=\"$1\"; shift\n"
            f"echo \"$host $*\" >> '{log}'\n"
            f"if [ -e '{during}' ]; then sh '{during}' < /dev/null; rm -f '{during}'; fi\n"
            "case \"$*\" in\n"
            "  *pkill*) cat > /dev/null ;;\n"
            f"  *) HOME='{self.remote}' exec sh -c \"$*\" ;;\n"
            "esac\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return log

    def watch(self):
        return self.relay("watch", "--once")

    def relay_on_host(self, *args):
        return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True,
                              env=dict(self.env(), HOME=str(self.remote)))

    def state(self, remote=False):
        path = (self.remote if remote else self.root) / ".config" / "claude-relay" / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def write_state(self, data, remote=False):
        path = (self.remote if remote else self.root) / ".config" / "claude-relay" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def resume_list(self):
        return json.loads((self.root / ".config" / "claude-relay" / "resume.json").read_text())


class LimitEntryTests(unittest.TestCase):
    def test_usage_limit_with_reset_time(self):
        self.assertEqual(relay.limit_from_entry(limit_entry(100, 5000)), (5000, "seven_day"))
        self.assertEqual(relay.limit_from_entry(limit_entry(100, 7000, kind="five_hour")), (7000, "five_hour"))

    def test_reset_time_from_error_params(self):
        e = limit_entry(100, 5000)
        del e["quotaLimits"]
        e["apiErrorParams"] = {"rate_limit_info": {"status": "rejected", "resetsAt": 6000,
                                                   "rateLimitType": "five_hour"}}
        self.assertEqual(relay.limit_from_entry(e), (6000, "five_hour"))

    def test_not_a_usage_limit(self):
        self.assertIsNone(relay.limit_from_entry(capacity_entry(100)))
        self.assertIsNone(relay.limit_from_entry(reply_entry(100)))
        e = limit_entry(100, 5000)
        e["error"] = "server_error"
        self.assertIsNone(relay.limit_from_entry(e))
        e = capacity_entry(100)  # a 429 that does not name the usage limit
        e["message"]["content"][0]["text"] = "API Error: Request rejected (429)"
        self.assertIsNone(relay.limit_from_entry(e))

    def test_usage_limit_without_details(self):
        e = limit_entry(100, 5000)
        del e["quotaLimits"]
        self.assertEqual(relay.limit_from_entry(e), (None, None))


class MergeMarksTests(unittest.TestCase):
    def test_a_clear_drops_older_marks_on_both_sides(self):
        # A host learns of a clear: its own older mark (no `since`, as 2.2.1 wrote it) goes.
        st = {"exhausted": {"a": {"until": 500, "reason": "token rejected"}, "b": 400}, "cleared": {}}
        relay.merge_marks(st, {"exhausted": {"c": {"until": 900, "reason": "x", "since": 300}},
                               "cleared": {"a": 100, "c": 200}})
        self.assertEqual(st["exhausted"], {"b": 400, "c": {"until": 900, "reason": "x", "since": 300}})
        # A mark read before a clear that happened meanwhile does not come back; the later clear wins.
        relay.merge_marks(st, {"exhausted": {"a": {"until": 600, "reason": "y", "since": 50}}, "cleared": {"a": 90}})
        self.assertNotIn("a", st["exhausted"])
        self.assertEqual(st["cleared"], {"a": 100, "c": 200})
        # Among the marks made after the clear, the later reset wins.
        relay.merge_marks(st, {"exhausted": {"a": {"until": 700, "reason": "z", "since": 150},
                                             "c": {"until": 800, "reason": "w", "since": 400}}})
        self.assertEqual(st["exhausted"]["a"]["until"], 700)
        self.assertEqual(st["exhausted"]["c"]["until"], 900)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.h = WatchHome()
        self.now = time.time()
        self.h.desktop_login("acctA")
        self.h.add_card("acctA", "orgA", "S1", title="stopped on the limit")
        self.h.add_card("acctA", "orgA", "S2", title="finished")
        self.h.add_card("acctA", "orgA", "S3", title="resumed by hand")
        self.desktop_log = self.h.fake_desktop(NOT_AN_ANCESTOR)
        self.ssh_log = self.h.fake_remote_ssh()

    def tearDown(self):
        self.h.cleanup()

    def first_pass(self):
        r = self.h.watch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_first_pass_remembers_the_account_and_ignores_older_errors(self):
        self.h.transcript("S1", [user_entry(self.now - 700), limit_entry(self.now - 650, self.now + 3600)])
        self.first_pass()
        st = self.h.state()
        self.assertEqual(st["watch"]["restored"], "acctA")
        self.assertEqual(st.get("exhausted"), {})
        self.assertNotIn("osascript", self.desktop_log.read_text() if self.desktop_log.exists() else "")

    def test_marks_the_desktop_account_exhausted(self):
        self.first_pass()
        t = time.time()
        resets = int(t + 3600)
        self.h.transcript("S1", [user_entry(t), limit_entry(t + 1, resets)], age=1)
        self.h.transcript("S2", [capacity_entry(t + 1)], age=1)
        self.h.transcript("CLI1", [limit_entry(t + 1, resets, entrypoint="cli")], age=1)
        r = self.h.watch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.h.state()["exhausted"],
                         {"acctA": {"until": resets, "reason": "hit its weekly limit", "since": int(t + 1)}})
        self.assertIn("acctA hit its weekly limit", r.stdout)

    def test_linked_name_and_expired_limits(self):
        self.assertEqual(self.h.relay("accounts", "link", "work", "acctA").returncode, 0)
        self.first_pass()
        t = time.time()
        self.h.transcript("S1", [limit_entry(t + 1, t - 1)], age=1)  # already reset
        self.h.watch()
        self.assertEqual(self.h.state()["exhausted"], {})
        self.h.transcript("S2", [limit_entry(t + 2, int(t + 600), kind="five_hour")], age=1)
        r = self.h.watch()
        self.assertIn("work hit its 5-hour limit", r.stdout)
        self.assertEqual(self.h.state()["exhausted"]["work"]["until"], int(t + 600))

    def test_remote_limit_and_state_are_synced_both_ways(self):
        self.h.relay("accounts", "link", "work", "acctA")
        self.h.relay("remote", "add", "devbox")
        remote_cfg = self.h.remote / ".config" / "claude-relay"
        remote_cfg.mkdir(parents=True)
        (remote_cfg / "state.json").write_text(json.dumps(
            {"active": "home", "usage": {},
             "exhausted": {"home": {"until": self.now + 900, "reason": "hit its usage limit"}}}))
        self.first_pass()
        t = time.time()
        resets = int(t + 3600)
        self.h.transcript("R1", [limit_entry(t + 1, resets)], age=1, remote=True)
        r = self.h.watch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("work hit its weekly limit", r.stdout)
        self.assertEqual(self.h.state()["exhausted"]["work"]["until"], resets)
        self.assertEqual(self.h.state()["exhausted"]["home"]["until"], self.now + 900)
        self.assertEqual(self.h.state(remote=True)["exhausted"]["work"]["until"], resets)
        self.assertIn("devbox python3 - _sync", self.ssh_log.read_text())

    def mark_on_both_machines(self, reason):
        """A mark for `great` on the Mac and on the host, the way 2.2.1 wrote it (no `since`)."""
        self.h.relay("remote", "add", "devbox")
        self.h.relay("accounts", "link", "great", "acctG")
        mark = {"until": self.now + 86400, "reason": reason}
        for remote in (False, True):
            self.h.write_state({"active": "great", "usage": {}, "exhausted": {"great": mark}}, remote=remote)
        self.first_pass()

    def marks_after_two_passes(self):
        for _ in range(2):
            r = self.h.watch()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.h.state()["exhausted"], self.h.state(remote=True)["exhausted"]

    def test_reset_on_the_mac_survives_watch_with_the_mark_still_on_the_host(self):
        self.mark_on_both_machines("token rejected")
        self.assertEqual(self.h.relay("reset", "great").returncode, 0)
        self.assertNotIn("great", self.h.state()["exhausted"])
        self.assertIn("great", self.h.state(remote=True)["exhausted"])
        self.assertEqual(self.marks_after_two_passes(), ({}, {}))
        self.assertGreater(self.h.state(remote=True)["cleared"]["great"], self.now)

    def test_reset_during_a_watch_pass_is_not_undone(self):
        self.mark_on_both_machines("token rejected")
        # `reset` runs while this pass waits on ssh, after it read the state it will write back.
        (self.h.root / "during-ssh").write_text(f"'{sys.executable}' '{CLI}' reset great\n")
        r = self.h.watch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.h.root / "during-ssh").exists())
        self.assertIn("great", self.h.state(remote=True)["exhausted"])  # the host got the old snapshot
        self.assertNotIn("great", self.h.state()["exhausted"])
        self.assertEqual(self.marks_after_two_passes(), ({}, {}))

    def test_use_on_the_mac_clears_the_mark_everywhere(self):
        self.mark_on_both_machines("hit its weekly limit")
        self.assertEqual(self.h.relay("use", "great").returncode, 0)
        self.assertEqual(self.marks_after_two_passes(), ({}, {}))

    def test_reset_on_the_host_clears_the_mark_on_the_mac(self):
        self.mark_on_both_machines("token rejected")
        self.assertEqual(self.h.relay_on_host("reset", "great").returncode, 0)
        self.assertEqual(self.marks_after_two_passes(), ({}, {}))

    def test_plain_reset_covers_a_mark_only_on_the_host(self):
        self.h.relay("remote", "add", "devbox")
        self.h.relay("accounts", "link", "great", "acctG")
        self.h.write_state({"active": "great", "usage": {},
                            "exhausted": {"great": {"until": self.now + 86400, "reason": "token rejected"}}},
                           remote=True)
        self.assertEqual(self.h.relay("reset").returncode, 0)
        self.assertEqual(self.marks_after_two_passes(), ({}, {}))

    def test_a_new_token_lifts_a_rejected_token_mark_everywhere(self):
        self.mark_on_both_machines("token rejected")
        token_file = self.h.root / "great.token"
        token_file.write_text(TOKEN_G + "\n")
        self.assertEqual(self.h.relay("accounts", "add", "great", "--token-file", str(token_file)).returncode, 0)
        self.assertEqual(self.marks_after_two_passes(), ({}, {}))

    def test_a_new_token_keeps_a_usage_limit_mark(self):
        self.mark_on_both_machines("hit its weekly limit")
        token_file = self.h.root / "great.token"
        token_file.write_text(TOKEN_G + "\n")
        self.assertEqual(self.h.relay("accounts", "add", "great", "--token-file", str(token_file)).returncode, 0)
        mac, host = self.marks_after_two_passes()
        self.assertEqual((mac["great"]["reason"], host["great"]["reason"]),
                         ("hit its weekly limit", "hit its weekly limit"))

    def test_only_a_limit_after_the_reset_marks_the_account_again(self):
        self.h.relay("remote", "add", "devbox")
        self.first_pass()
        st = self.h.state()
        st["watch"]["history"] = [[self.now - 600, "acctA"]]  # as if `watch` had run for 10 minutes
        self.h.write_state(st)
        t = time.time()
        resets = int(t + 3600)
        self.h.transcript("S1", [limit_entry(t - 5, resets)], age=1)  # before the reset, seen after it
        self.assertEqual(self.h.relay("reset", "acctA").returncode, 0)
        r = self.h.watch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("hit its weekly limit", r.stdout)
        self.assertEqual(self.h.state()["exhausted"], {})
        t = time.time()
        self.h.transcript("S2", [limit_entry(t + 1, resets)], age=1)
        r = self.h.watch()
        self.assertIn("acctA hit its weekly limit", r.stdout)
        self.assertEqual(self.h.state()["exhausted"]["acctA"]["until"], resets)
        self.assertEqual(self.h.state(remote=True)["exhausted"]["acctA"]["until"], resets)

    def test_publishes_the_claude_desktop_account_everywhere(self):
        self.h.relay("accounts", "link", "work", "acctA")
        self.h.relay("remote", "add", "devbox")
        self.first_pass()
        self.assertEqual(self.h.state()["desktop"], "work")
        self.assertEqual(self.h.state(remote=True)["desktop"], "work")
        self.h.relay("accounts", "link", "home", "acctB")
        self.h.desktop_login("acctB")
        self.h.watch()
        self.assertEqual(self.h.state()["desktop"], "home")
        self.assertEqual(self.h.state(remote=True)["desktop"], "home")

    def test_remote_install_copies_the_script_and_the_account_names(self):
        token = "sk-ant-oat01-" + "w" * 95
        token_file = self.h.root / "work.token"
        token_file.write_text(token + "\n")
        self.assertEqual(self.h.relay("accounts", "add", "work", "--token-file", str(token_file)).returncode, 0)
        self.h.relay("accounts", "link", "work", "acctA")
        self.h.relay("accounts", "link", "home", "acctB")
        r = self.h.relay("remote", "install", "devbox")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        installed = self.h.remote / ".local" / "bin" / "claude-relay"
        self.assertEqual(installed.read_text(), Path(relay.__file__).read_text())
        self.assertTrue(os.access(installed, os.X_OK))
        cfg = json.loads((self.h.remote / ".config" / "claude-relay" / "config.json").read_text())
        self.assertEqual({a["name"]: a.get("desktop_account") for a in cfg["accounts"]},
                         {"work": "acctA", "home": "acctB"})
        # Tokens stay on this machine: the host gets names and links only.
        self.assertFalse((self.h.remote / ".config" / "claude-relay" / "tokens").exists())
        self.assertNotIn(token, self.ssh_log.read_text())
        self.assertIn("claude-relay accounts add home", r.stdout)
        self.assertEqual(self.h.relay("remote", "install", "devbox").returncode, 0)  # can run again

    def test_unreachable_host_does_not_stop_the_pass(self):
        self.h.relay("remote", "add", "devbox")
        (self.h.bin / "ssh").write_text("#!/bin/sh\necho 'ssh: connect timed out' >&2\nexit 255\n")
        r = self.first_pass()
        self.assertIn("Could not reach devbox", r.stdout)

    def switch_after_limit(self, quiet):
        self.h.relay("remote", "add", "devbox")
        self.first_pass()
        t = time.time()
        resets = int(t + 3600)
        self.h.transcript("S1", [user_entry(t - 900), limit_entry(t + 1, resets)], age=1)
        self.h.transcript("S2", [user_entry(t - 900), reply_entry(t - 800)], age=1)
        self.h.transcript("S3", [limit_entry(t + 1, resets), user_entry(t + 2), reply_entry(t + 3)], age=1)
        self.h.watch()  # sees the limits on acctA
        if quiet:  # as if the sessions had not written for 2 minutes
            old = time.time() - 120
            for cli in ("S1", "S2", "S3"):
                os.utime(self.h.projects / f"{cli}.jsonl", (old, old))
        self.h.desktop_login("acctB")
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True, exist_ok=True)
        return self.h.watch()

    def test_restores_after_the_account_change_and_lists_sessions_to_resume(self):
        r = self.switch_after_limit(quiet=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.desktop_log.read_text()
        self.assertIn('osascript -e quit app "Claude"', log)
        self.assertIn("open -a Claude", log)
        self.assertEqual(sorted(c["cliSessionId"] for c in self.h.cards_of("acctB", "orgB")), ["S1", "S2", "S3"])
        self.assertIn("pkill", self.ssh_log.read_text())
        resume = self.h.resume_list()
        self.assertEqual([s["cliSessionId"] for s in resume["sessions"]], ["S1"])
        self.assertEqual(resume["sessions"][0]["sessionId"], "local_S1")
        self.assertEqual(resume["sessions"][0]["host"], "local")
        self.assertEqual(self.h.state()["watch"]["restored"], "acctB")
        self.assertIn("1 session(s) stopped on the limit. List: ", r.stdout)  # nothing to do by hand
        # A one-time Desktop scheduled task, already due, resumes them when the app reopens.
        path = self.h.cards / "acctB" / "orgB" / "scheduled-tasks.json"
        tasks = json.loads(path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)  # as Claude Desktop keeps it
        task = next(t for t in tasks["scheduledTasks"] if t["id"] == "claude-relay-resume")
        self.assertTrue(task["enabled"])
        self.assertLessEqual(task["fireAt"], time.time() * 1000)
        self.assertEqual(task["cwd"], str(self.h.root / ".config" / "claude-relay"))
        skill = Path(task["filePath"]).read_text()
        self.assertTrue(task["filePath"].startswith(str(self.h.root / ".claude" / "scheduled-tasks")))
        self.assertIn("resume.json", skill)
        self.assertIn("Continue exactly where you left off", skill)
        again = self.h.watch()  # nothing left to do
        self.assertNotIn("Quitting Claude Desktop", again.stdout)

    def test_existing_scheduled_tasks_are_kept(self):
        dest = self.h.cards / "acctB" / "orgB"
        dest.mkdir(parents=True)
        (dest / "scheduled-tasks.json").write_text(json.dumps(
            {"scheduledTasks": [{"id": "daily", "cronExpression": "30 8 * * *", "enabled": True}],
             "recordedSkips": {}}))
        self.h.add_tasks("acctA", "orgA", [{"id": "weekly", "cronExpression": "0 9 * * 1", "enabled": True}])
        self.switch_after_limit(quiet=True)
        tasks = json.loads((dest / "scheduled-tasks.json").read_text())
        self.assertEqual([t["id"] for t in tasks["scheduledTasks"]], ["daily", "weekly", "claude-relay-resume"])
        self.assertEqual(tasks["recordedSkips"], {})
        self.assertEqual((dest / "scheduled-tasks.json").stat().st_mode & 0o777, 0o600)

    def assert_unreadable_scheduled_tasks_are_left_alone(self, content):
        path = self.h.cards / "acctB" / "orgB" / "scheduled-tasks.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        r = self.switch_after_limit(quiet=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(path.read_bytes(), content)
        self.assertIn("so the resume task was not added", r.stdout)
        self.assertFalse((self.h.root / ".claude" / "scheduled-tasks" / "claude-relay-resume").exists())
        self.assertIn("open -a Claude", self.desktop_log.read_text())  # the switch still finishes
        # The same text goes to the macOS notification, so it says that the sessions will not resume.
        line = next(l for l in r.stdout.splitlines() if "Sessions moved to" in l)
        self.assertIn("1 session(s) stopped on the limit. Resume them by hand: the list is in "
                      f"{self.h.root / '.config' / 'claude-relay' / 'resume.json'}.", line)

    def test_unreadable_scheduled_tasks_file_is_left_alone(self):
        self.assert_unreadable_scheduled_tasks_are_left_alone(b"{not json")

    def test_scheduled_tasks_that_are_not_a_list_are_left_alone(self):
        self.assert_unreadable_scheduled_tasks_are_left_alone(b'{"scheduledTasks": {"daily": {}}}')

    def test_resume_task_that_cannot_be_written_does_not_stop_the_switch(self):
        (self.h.root / ".claude" / "scheduled-tasks").write_text("")  # a file where its folder goes
        r = self.switch_after_limit(quiet=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Could not write the resume task", r.stdout)
        self.assertIn("open -a Claude", self.desktop_log.read_text())
        self.assertEqual(self.h.state()["watch"]["restored"], "acctB")
        self.assertFalse((self.h.cards / "acctB" / "orgB" / "scheduled-tasks.json").exists())
        line = next(l for l in r.stdout.splitlines() if "Sessions moved to" in l)
        self.assertIn("1 session(s) stopped on the limit. Resume them by hand: the list is in "
                      f"{self.h.root / '.config' / 'claude-relay' / 'resume.json'}.", line)

    def test_no_resume_task_without_stopped_sessions(self):
        self.h.relay("remote", "add", "devbox")
        self.first_pass()
        self.h.desktop_login("acctB")
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True)
        r = self.h.watch()
        self.assertIn("0 session(s) stopped on the limit", r.stdout)
        self.assertFalse((self.h.cards / "acctB" / "orgB" / "scheduled-tasks.json").exists())

    def test_restore_waits_while_desktop_sessions_write(self):
        r = self.switch_after_limit(quiet=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("waiting until no session has written for 60 s", r.stdout)
        self.assertNotIn("osascript", self.desktop_log.read_text() if self.desktop_log.exists() else "")
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])

    def test_restore_waits_for_unreachable_hosts(self):
        self.h.relay("remote", "add", "devbox")
        self.first_pass()
        (self.h.bin / "ssh").write_text("#!/bin/sh\necho 'ssh: connect timed out' >&2\nexit 255\n")
        self.h.desktop_login("acctB")
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True)
        r = self.h.watch()
        self.assertIn("waiting to reach devbox", r.stdout)
        self.assertEqual(self.h.cards_of("acctB", "orgB"), [])

    def test_gives_up_after_three_failed_moves(self):
        self.first_pass()
        self.h.fake_desktop(NOT_AN_ANCESTOR, after_quit=3)  # pgrep fails after the quit request
        self.h.desktop_login("acctB")
        (self.h.cards / "acctB" / "orgB").mkdir(parents=True)
        path = self.h.root / ".config" / "claude-relay" / "state.json"
        for _ in range(3):
            st = json.loads(path.read_text())
            st["watch"].pop("retry_at", None)  # skip the 5-minute wait
            path.write_text(json.dumps(st))
            r = self.h.watch()
        self.assertIn("Could not move the sessions after 3 tries", r.stdout)
        self.assertEqual(self.h.state()["watch"]["gave_up"], "acctB")
        self.assertIn("open -a Claude", (self.h.root / "desktop.log").read_text())  # not left closed
        again = self.h.watch()
        self.assertNotIn("Quitting Claude Desktop", again.stdout)

    def test_restore_waits_for_the_code_tab(self):
        self.first_pass()
        self.h.desktop_login("acctB")
        r = self.h.watch()
        self.assertIn("Open the Code tab", r.stdout)
        self.assertEqual(self.h.state()["watch"]["restored"], "acctA")


@unittest.skipUnless(sys.platform == "darwin", "launchd agent")
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.h = FakeHome()
        self.log = self.h.root / "launchctl.log"
        script = self.h.bin / "launchctl"
        script.write_text(f"#!/bin/sh\necho \"$@\" >> '{self.log}'\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.plist = self.h.root / "Library" / "LaunchAgents" / "io.github.guedesdiogo.claude-relay.plist"

    def tearDown(self):
        self.h.cleanup()

    def test_install_and_uninstall(self):
        r = self.h.relay("service", "install")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = plistlib.loads(self.plist.read_bytes())
        self.assertEqual(data["ProgramArguments"][-1], "watch")
        self.assertTrue(data["KeepAlive"])
        self.assertTrue(data["StandardOutPath"].endswith("watch.log"))
        self.assertIn(f"bootstrap gui/{os.getuid()} {self.plist}", self.log.read_text())
        r = self.h.relay("service", "uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.plist.exists())
        self.assertIn(f"bootout gui/{os.getuid()}/io.github.guedesdiogo.claude-relay", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
