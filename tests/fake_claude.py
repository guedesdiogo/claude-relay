#!/usr/bin/env python3
"""A stand-in for the `claude` binary used by the tests.

It records how it was started, then plays a scenario chosen with FAKE_SCENARIO by calling
the status line and hooks that claude-relay passed in --settings, exactly as Claude Code would.
"""
import json
import os
import signal
import subprocess
import sys
import time

LOG = os.environ["FAKE_LOG"]
SCENARIO = os.environ.get("FAKE_SCENARIO", "exit")


def log(entry):
    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def settings():
    argv = sys.argv[1:]
    if "--settings" in argv:
        return json.loads(argv[argv.index("--settings") + 1])
    return {}


def run_cmd(command, payload):
    return subprocess.run(command, shell=True, input=json.dumps(payload), capture_output=True, text=True,
                          env=os.environ).stdout


def hook(event, payload):
    for group in settings().get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            run_cmd(h["command"], payload)


def statusline(payload):
    sl = settings().get("statusLine")
    return run_cmd(sl["command"], payload) if sl else ""


def wait_for_term():
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(143))
    time.sleep(float(os.environ.get("FAKE_WAIT", "30")))
    sys.exit(0)


def main():
    with open(LOG) as f:
        call = sum(1 for line in f if '"argv"' in line)
    argv = sys.argv[1:]
    clean = argv[:argv.index("--settings")] + argv[argv.index("--settings") + 2:] if "--settings" in argv else argv
    log({"call": call, "argv": clean, "token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"),
         "account": os.environ.get("CLAUDE_RELAY_ACCOUNT"),
         "api_key": os.environ.get("ANTHROPIC_API_KEY")})
    future = int(time.time()) + 3600
    sid = "sess-1"

    if call > 0 or SCENARIO == "exit":
        out = statusline({"session_id": sid, "rate_limits": {"five_hour": {"used_percentage": 3,
                                                                             "resets_at": future}}})
        log({"call": call, "statusline": out})
        sys.exit(0)

    hook("SessionStart", {"session_id": sid, "hook_event_name": "SessionStart"})
    if SCENARIO == "threshold":
        out = statusline({"session_id": sid, "rate_limits": {
            "five_hour": {"used_percentage": 96, "resets_at": future},
            "seven_day": {"used_percentage": 40, "resets_at": future + 86400}}})
        log({"call": call, "statusline": out})
        hook("Stop", {"session_id": sid, "hook_event_name": "Stop"})
        wait_for_term()
    elif SCENARIO == "marked-elsewhere":
        # `claude-relay watch` (or another machine's sync) marks this account exhausted mid-run.
        path = os.path.join(os.environ["CLAUDE_RELAY_HOME"], "state.json")
        with open(path) as f:
            state = json.load(f)
        state["exhausted"][os.environ["CLAUDE_RELAY_ACCOUNT"]] = {"until": future, "reason": "hit its weekly limit"}
        with open(path, "w") as f:
            json.dump(state, f)
        hook("Stop", {"session_id": sid, "hook_event_name": "Stop"})
        wait_for_term()
    elif SCENARIO == "desktop-switch":
        # `claude-relay watch` publishes that Claude Desktop is now on another account.
        path = os.path.join(os.environ["CLAUDE_RELAY_HOME"], "state.json")
        with open(path) as f:
            state = json.load(f)
        state["desktop"], state["desktop_at"] = os.environ.get("FAKE_DESKTOP", "b"), time.time()
        with open(path, "w") as f:
            json.dump(state, f)
        hook("Stop", {"session_id": sid, "hook_event_name": "Stop"})
        wait_for_term()
    elif SCENARIO == "below":
        statusline({"session_id": sid, "rate_limits": {"five_hour": {"used_percentage": 50, "resets_at": future}}})
        hook("Stop", {"session_id": sid, "hook_event_name": "Stop"})
        sys.exit(0)
    elif SCENARIO == "limit":
        statusline({"session_id": sid, "rate_limits": {"seven_day": {"used_percentage": 100,
                                                                     "resets_at": future}}})
        hook("StopFailure", {"session_id": sid, "hook_event_name": "StopFailure", "error": "rate_limit",
                             "last_assistant_message": "You've hit your weekly limit · resets Mon 12:00am"})
        wait_for_term()
    elif SCENARIO == "capacity":
        hook("StopFailure", {"session_id": sid, "hook_event_name": "StopFailure", "error": "rate_limit",
                             "last_assistant_message": "Request rejected (429) · this may be a temporary capacity issue"})
        sys.exit(0)
    elif SCENARIO == "auth":
        hook("StopFailure", {"session_id": sid, "hook_event_name": "StopFailure", "error": "authentication_failed",
                             "last_assistant_message": "Failed to authenticate. API Error: 401"})
        wait_for_term()
    elif SCENARIO == "print-limit-nohook":
        # Like real Claude Code in -p mode: it exits before the StopFailure hook can finish,
        # so claude-relay has to read the error from the transcript.
        transcript = os.path.join(os.path.dirname(LOG), "sess-1.jsonl")
        with open(transcript, "w") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit",
                                "message": {"role": "assistant", "content": [
                                    {"type": "text", "text": "You've hit your session limit · resets 3pm"}]}}) + "\n")
        hook("SessionStart", {"session_id": sid, "transcript_path": transcript})
        print("API Error: You've hit your session limit")
        sys.exit(1)
    elif SCENARIO == "print-limit":
        hook("StopFailure", {"session_id": sid, "hook_event_name": "StopFailure", "error": "rate_limit"})
        print("API Error: You've hit your session limit")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
