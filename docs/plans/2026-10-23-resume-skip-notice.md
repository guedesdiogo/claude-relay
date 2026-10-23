# The notification says when the resume task was not added (2.2.4)

Problem, left open by 2.2.3: when the account's `scheduled-tasks.json` exists but cannot be read,
`register_resume_task()` leaves it alone and warns in `watch.log`. That log is the launchd agent's
stdout, which users rarely read. The macOS notification still says `Sessions moved to X; N
session(s) stopped on the limit.`, so they expect the sessions to resume and they never do.

## Plan

1. `register_resume_task()` returns whether it added the task.
2. When it did not, `watch_pass()` appends `Resume them by hand: the list is in <resume.json>.` to
   the message, and that one message goes both to the log line and to the notification. The
   instruction comes before the path, so a truncated banner still shows it.
3. With no stopped sessions there is no task to add, and the message stays as it was.

## Left open

- If `register_resume_task()` raises (an I/O error writing `SKILL.md` or the task list), the
  exception leaves `watch_pass()` before `open_desktop()`. The `watch` loop logs it and goes on, but
  that pass does not reopen Claude Desktop. This predates 2.2.3.
