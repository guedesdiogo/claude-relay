# The resume task leaves the task list alone (2.2.3)

Problem, found in the 2.1.1 review: `register_resume_task()`, which `watch` calls after a switch to
add the one-time `claude-relay-resume` task, writes the account's
`claude-code-sessions/<account>/<org>/scheduled-tasks.json` with mode 0644, while Claude Desktop
keeps it at 0600 (checked on the Mac on 2026-10-23). When the file does not parse as an object, or
its `scheduledTasks` is not a list, it replaces the file with only the resume task, so the account
loses its scheduled tasks.

## Plan

1. Write the file with `write_json`'s default 0600, as `copy_scheduled_tasks()` does.
2. Same guard as `copy_scheduled_tasks()`: a missing file is created, but a file that exists and
   cannot be read is left as it is. `watch` warns that the resume task was not added and points to
   `resume.json`; the switch still finishes and the app reopens.
3. The check runs before the task's `SKILL.md` is written, so nothing is left behind when the task
   is not added.

## Left open

- Entries of `scheduledTasks` that are not objects are still dropped when the resume task is
  added; `copy_scheduled_tasks()` keeps them.
