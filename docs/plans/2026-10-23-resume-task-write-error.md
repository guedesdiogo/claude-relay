# A resume task that cannot be written does not stop the switch (2.2.5)

Problem, left open by 2.2.4 and older than 2.2.3: after `watch` moves the sessions, it registers
the resume task while Claude Desktop is still closed. `register_resume_task()` writes
`~/.claude/scheduled-tasks/claude-relay-resume/SKILL.md` and the account's `scheduled-tasks.json`.
If either write raises an `OSError` (a permission error, a file in the way), the exception leaves
`watch_pass()` before `open_desktop()`. The `watch` loop logs it and goes on, but that pass does not
reopen the app, sends no notification and does not save the watch state.

## Plan

1. Test first: `~/.claude/scheduled-tasks` is a file in the fake HOME. After a switch the app is
   reopened, `restored` is the new account, and the summary line says to resume the sessions by
   hand.
2. `register_resume_task()` catches `OSError` around its writes, logs it and returns False, like the
   unreadable-file skip. `watch_pass()` then finishes the switch and the notification carries the
   hand-resume instruction added in 2.2.4.
3. README, `watch` step 5: when the task cannot be added, the notification says to resume the
   sessions by hand from `resume.json`.

## Left open

- `write_resume_list()` writes `resume.json` in the same window, before the task. An I/O error there
  still skips `open_desktop()`.
- If `SKILL.md` is written but `scheduled-tasks.json` is not, the prompt file stays behind. No task
  points at it, and the next registration overwrites it.
- Only `OSError` is caught. A `UnicodeEncodeError` from a lone surrogate in the task list still
  escapes.
- A failed write is not retried on the next pass: the sessions leave `pending`, as with the
  unreadable-file skip, and `resume.json` is the list to resume by hand.
