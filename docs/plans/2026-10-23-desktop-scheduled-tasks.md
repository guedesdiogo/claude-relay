# Scheduled tasks follow the account (2.1.1)

Problem: Claude Desktop keeps one list of scheduled tasks per account, so after a switch the
recurring tasks of the previous account stop running. On 2026-10-23 the daily `env-update-daily`
task was registered only in the account the app was no longer signed in to.

Format observed on 2026-10-23: the prompt of each task is in `~/.claude/scheduled-tasks/<id>/SKILL.md`
(shared), and each account registers its tasks in
`claude-code-sessions/<account>/<org>/scheduled-tasks.json` as
`{"scheduledTasks": [{"id", "cronExpression" | "fireAt" (epoch ms), "enabled", "filePath",
"createdAt", "cwd", "displayName"?, "permissionMode"?, "permissionModeCarried"?, "lastRunAt"?,
"lastScheduledFor"?, "notifySessionId"?}], "recordedSkips": {}, "sundayAliasBoundaryStamped",
"dayFieldsOrBoundaryStamped"}`.

## Plan

1. `claude-relay desktop` adds the recurring tasks (`cronExpression`) of the other accounts'
   files to the destination's file, once per id, newest file first. Tasks the destination already
   has stay as they are, and so do its other fields (`recordedSkips` is per account).
2. Not copied: one-time tasks (`fireAt`), `claude-relay-resume`, and the record of the last run
   in the other account (`lastRunAt`, `lastScheduledFor`, `notifySessionId`).
3. Same guards as the cards: only with the app closed, nothing written on `--dry-run`, covered by
   the backup of the card folder. A destination file that does not parse is left alone, with a
   warning. `watch` gets this for free, since it runs `desktop`.

## Left open

- Deleting a task in one account does not delete it in the others, so it comes back on the next
  switch (the README says to delete it in each account).
- Whether Claude Desktop runs a missed slot at once for a copied task that has no
  `lastScheduledFor` is not verified.
