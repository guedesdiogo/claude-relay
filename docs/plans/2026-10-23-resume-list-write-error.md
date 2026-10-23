# A resume list that cannot be written does not stop the switch (2.2.6)

Problem, left open by 2.2.5: after `watch` moves the sessions, `write_resume_list()` writes
`~/.config/claude-relay/resume.json` while Claude Desktop is still closed, before the resume task
and `open_desktop()`. If that write raises an `OSError`, the exception leaves `watch_pass()`: that
pass does not reopen the app, sends no notification and does not save the watch state.

## Depth

A `try`/`finally` around the post-move block that always calls `open_desktop()` would reopen the
app, but the pass would still end before the state save. `restored` would stay on the old account,
so the next pass would quit the app and move the sessions again, every pass while the write fails.
So the error is handled where it happens, as 2.2.5 does for the task writes.

Without `resume.json` there is also no resume task: the task reads that file, and an older one from
a previous switch may still be there, so the task would message the wrong sessions.

## Plan

1. Test first: a folder where `resume.json` goes in the fake HOME (`os.replace` then fails;
   `state.json` in the same folder still writes). After a switch the app is reopened, `restored` is
   the new account, no task or prompt file is written, and the summary line names the sessions
   instead of `resume.json`.
2. `write_resume_list()` catches `OSError` around the write, logs it and returns the sessions with
   whether the file was written. `watch_pass()` skips the task when it was not, and the summary line
   (which is also the notification) says `Resume them by hand: "<title>", ...`, falling back to the
   session id for a card without a title.
3. README, `watch` step 5: when `resume.json` cannot be written, the notification names the
   sessions to resume.

## Left open

- `write_json()` leaves `.resume.json.<pid>.tmp` behind when `os.replace` fails.
- Only `OSError` is caught. A `UnicodeEncodeError` from a lone surrogate in a title still escapes.
- An older `resume.json` stays on disk after a failed write; nothing reads it without the task.
- A long list of titles is cut short by the macOS notification; `watch.log` (or the terminal) has the
  whole line.
