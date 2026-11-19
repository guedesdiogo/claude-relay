# Make the resume task send its messages (2.3.3)

Problem, seen on 2026-11-19: after `watch` moved the sessions, the ones that had stopped on the
usage limit stayed stopped. They were resumed by hand.

What the files showed:

- Every run of the `claude-relay-resume` task since 2026-10-23 (10 runs, Claude Code 2.1.299 to
  2.1.326) messaged 0 sessions. Each one tried `SendMessage` and got "SendMessage cannot reach
  another session from a session nobody opened in this app; use the send_message tool". Then it tried
  `mcp__ccd_session_mgmt__send_message` and got "needs a person's approval, and nobody has opened this
  scheduled run". The task is registered without a permission mode, so its runs ask first, and nobody
  opens them.
- Claude Desktop saves a task created from a session in Auto mode as
  `"permissionMode": "auto", "permissionModeCarried": true` in `scheduled-tasks.json` (the
  `env-update-daily` task, and a test task created on 2026-11-19). A test run of such a task, started
  with `run_scheduled_task` and opened by nobody, called `send_message` on another session and got
  "delivery: queued", with no approval.
- At 13:53 `watch` moved the sessions to `genesis` and listed 10 stopped sessions. Claude Desktop was
  signed in to `diogoaguedes` 30 s later, before the task ran (it is still enabled, with no
  `lastRunAt`). The move at 13:58 listed 1 session, because the move at 13:53 had already taken the
  other 10 off `pending`.

## Plan

1. `register_resume_task` adds `"permissionMode": "auto", "permissionModeCarried": true` to the task.
   The prompt sends with `mcp__ccd_session_mgmt__send_message`, says not to use `SendMessage`, and
   says to message only the sessions in `resume.json`.
2. A move no longer takes the sessions it lists off `pending`. They leave it as before, once their
   transcript no longer ends on the limit. So a session the task did not resume goes into the next
   move's list.
3. A new limit error in a session that is already pending updates its account and time. Before, a
   session that stopped again after a move got a new entry under the new account. Now that the old
   entry stays, it has to take over the new account, or a move back to the first account would leave
   it out.
4. When it writes `resume.json`, `watch` removes the resume task from every other account's
   `scheduled-tasks.json`, and from all of them when the list is empty. The app is closed at that
   point. A task that has not run would otherwise fire at a later sign-in to its account and message
   the sessions of a list written for another account. Unreadable files are left alone.
5. README (`watch`, step 5) and CHANGELOG.

## Acceptance

- `tests/test_watch.py`: the task entry has the two fields; the prompt names `send_message` and
  tells the run not to use `SendMessage`.
- A second switch (acctB, then acctC) before the task runs lists the session again for acctC. acctB
  no longer has the task.
- A pending session that stops again on acctB counts as acctB's, and a switch back to acctA lists it.
  Without step 3 this test fails (`{'S1': 'acctA'} != {'S1': 'acctB'}`).
- A move removes stale resume tasks from other accounts, keeps their other tasks and the file's
  `0600` mode, and leaves an unreadable `scheduled-tasks.json` alone.

## Left open

- `send_message`'s own description calls it the older tool, "callable for now". If Claude Desktop
  removes it, the task cannot send again.
- Auto mode depends on the account and on Claude Desktop. Without it, the run asks first and sends
  nothing, as before.
- The test run was created by Claude Desktop's own tool. A task entry written by `watch` while the
  app is closed has the same fields, but only a real switch shows that the app honors them.
- A session that stopped on an account's own limit and comes back to that account is still not
  listed (`p["account"] != account`), as before.
