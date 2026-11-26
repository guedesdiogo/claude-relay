# Fill the fields a scheduled task copy lacks (2.3.4)

Problem, seen on 2026-11-26: the daily `manutencao-segundo-cerebro` task stalls on every run in one
of the three accounts. `copy_scheduled_tasks()` only adds a recurring task that the destination's
`scheduled-tasks.json` does not have, and it never touches one the destination already has.

What the files showed:

- Account `97aafdb9…` (org `798f0895…`) holds an old copy of `manutencao-segundo-cerebro` with no
  `permissionMode` and no `useWorktree`. In the other two accounts, the owner edited the same task in
  the app and saved it in Auto: `"permissionMode": "auto", "useWorktree": false`, with no
  `permissionModeCarried`, because the app drops it on an edit.
- A task with no mode runs in the default mode. Nobody opens its scheduled runs, so each run waits
  for an approval nobody gives. Before Auto was set in the other accounts, runs waited from 19 to
  1033 minutes on one compound Bash call. With Auto set, runs finished in about two minutes with no
  waits.
- In the same account, `env-update-daily` has `"permissionMode": "auto", "permissionModeCarried":
  true` and no `useWorktree`. In the newest account it has `"useWorktree": false`.
- Claude Desktop starts a session in a worktree only when `useWorktree === true` (seen in the app's
  bundle on 2026-11-26), so a missing `useWorktree` already runs without one.

## Plan

1. For a recurring task (`cronExpression`) the destination already had before this run, other than
   `claude-relay-resume`, `copy_scheduled_tasks()` fills the fields its entry lacks, where the key
   is absent or `null`:
   - `permissionMode`. When it fills the mode, it also takes `permissionModeCarried` from the same
     source copy, if that copy has it. A destination that already has a mode never gains
     `permissionModeCarried`: a carried mode can be switched off by a remote flag in the app, and a
     mode chosen in the editor cannot.
   - `useWorktree`.
2. The values come from the other accounts' copies of the same id, in the order the function already
   uses: newest file first, skipping the destination. The first copy that has a value for a missing
   field gives it; older copies then see the field as set.
3. A value that is set is never overwritten. `enabled`, `cronExpression`, `fireAt`, `cwd`,
   `displayName`, `filePath`, the run fields (`lastRunAt`, `lastScheduledFor`, `notifySessionId`) and
   the prompt file are never changed. One-time tasks and `claude-relay-resume` are not filled. Tasks
   this run copies in are not filled either: they arrive whole from the newest copy.
4. The file is written only when a task was copied or filled, with mode `0600`, and never on
   `--dry-run`. An unreadable destination file is left alone, as today. `desktop` prints a second
   line, "Filled missing fields in N scheduled task(s) from other accounts." ("Would fill" on
   `--dry-run`), after the existing "Copied" line, which stays as it is. N counts tasks, not fields.
5. README ("Scheduled tasks" and the `desktop` internals paragraph), CHANGELOG, and version 2.3.4.

## Alternatives left out

- **Newest file wins, for the whole task.** A file's mtime changes whenever Claude Desktop records a
  run in it. So a stale copy in an account that ran last would overwrite the values the owner set in
  the editor in the other accounts. Filling only missing fields cannot undo a choice someone made.
- **Copying the whole task over the destination's.** Same problem, and it would also carry over
  `enabled`, the schedule and the run record of another account.
- **Editing the stale copy by hand in the app.** It works once, but the next stale copy would need
  the same, and the owner chose on 2026-11-26 to fix it in the relay.

## Acceptance

- `tests/test_desktop.py`:
  - a destination task with no mode gets `auto` from another account, the file stays `0600`, and the
    output says "Filled missing fields in 1 scheduled task(s)";
  - a destination task with a mode keeps it and gains no `permissionModeCarried`;
  - `enabled`, `cronExpression`, `cwd`, `filePath` and `displayName` keep the destination's values,
    and a destination one-time task with a matching id is not filled;
  - with two sources that disagree, the newest file gives the missing fields, and a field the
    destination has keeps its value;
  - `--dry-run` prints "Would fill" and writes nothing;
  - a run with nothing to fill leaves the file untouched (same mtime);
  - an unreadable destination file is left alone, as today.
- Against the real folder,
  `claude-relay desktop --dry-run --existing-cards-only --account 97aafdb9-4569-43f6-9cda-4773ea86fd5d --org 798f0895-998b-47d1-95e8-850226f78e18`
  run from the branch reports "Would fill missing fields in 2 scheduled task(s)":
  `manutencao-segundo-cerebro` (`permissionMode`, `useWorktree`) and `env-update-daily`
  (`useWorktree`).

## Left open

- Only a real switch to `97aafdb9…` shows that the app honors a mode written while it was closed.
  The resume task (2.3.3) is the precedent: it is written the same way and runs in Auto.
- A field the destination has set and that differs from the other accounts is not reconciled. If
  someone sets Manual on purpose in one account, it stays Manual there.
- A task with no mode in every account stays without one.
