# Automatic account rotation (2.1 and 2.2)

Goal: when a Claude account hits its usage limit, move to the next account on the Mac and on the
SSH hosts at the same time, bring the Claude Desktop sessions along and resume the ones that
stopped, with as little manual work as possible.

## What claude-relay can do on its own

1. **Detect the limit on both machines.** `claude-relay watch` (a launchd agent on the Mac) reads
   new transcript lines every 30 s, locally and on each `remote` host over SSH (the script is piped
   to `python3 -`, so the host needs nothing installed for this). A Claude Desktop session that hit
   its limit leaves an entry with `entrypoint: "claude-desktop"`, `error: "rate_limit"` and
   `quotaLimits.resetsAt` (epoch seconds; verified with Claude Code 2.1.299). Temporary capacity
   429s are ignored.
2. **Share the state.** The exhausted account is recorded until its reset time and synced both ways
   with every host, so `claude-relay run` everywhere skips it. A running `claude-relay run` whose
   account gets marked exhausted switches at the end of the current turn.
3. **Notify.** "work hit its weekly limit until Thu 22 Oct 17:00. Sign Claude Desktop in to home."
4. **Restore after the sign-in.** When Claude Desktop's account changes, and no transcript has been
   written for 60 s on any machine, `watch` quits the app, copies the Code-tab cards, restarts the
   helpers on the SSH hosts and reopens the app. It runs under launchd, outside the app, so quitting
   the app does not stop it.
5. **List the sessions to resume** (`resume.json`): Desktop sessions whose last turn ended on the
   previous account's limit and that nobody has resumed since.
6. **(2.2) Resume them** from a Claude Desktop scheduled task that reads `resume.json` and sends
   each session a message, in waves. Needs a check first: that a scheduled task can message other
   sessions.
7. **(Optional, later)** switch before the limit from `api/oauth/usage`, if a `setup-token` token is
   allowed to read it.

## What still needs the user

- Every switch: sign Claude Desktop in to the other account (there is no supported way to automate
  the sign-in).
- Once per account per year: `claude setup-token` and `claude-relay accounts add` on each machine
  where `claude-relay run` is used.
- Once: `claude-relay accounts link NAME DESKTOP_UUID` for each account, and
  `claude-relay service install` on the Mac.
- The first time the resume task runs: allow it to send messages.

## Left out, and why

- Running Desktop sessions on another account's token (a wrapper around the `ccd-cli` binary
  Desktop deploys, or `CLAUDE_CODE_OAUTH_TOKEN` in settings): Desktop redeploys that binary (its
  folder is content-hashed), `setup-token` tokens only allow model requests (Remote Control and
  sync need more), and the app would show one account while billing another.
- Copying Desktop's encrypted `oauth:tokenCache` between accounts: it touches the app's credential
  store, is undocumented and can break with any update.
- `claude --resume` from outside on Desktop sessions: two processes would write one transcript.

## Risk

Rotating accounts automatically to get past usage limits is the pattern automated abuse systems
look for, and each subscription's payer has its own rules. The README says so.

## Check for step 6 (done 2026-10-23)

A scheduled task run has `SendMessage`, `send_message`, `list_sessions` and `get_session`; Bash
asked for permission in the default mode. The task's prompt lives in
`~/.claude/scheduled-tasks/<id>/SKILL.md`; each account registers its tasks in
`claude-code-sessions/<account>/<org>/scheduled-tasks.json` as
`{"scheduledTasks": [{"id", "fireAt": <epoch ms>, "enabled", "filePath", "cwd", ...}]}`, and the
app runs a due one-time task when it opens. So `watch` registers a due task, with RELAY_HOME as its
folder (Read without a prompt), while the app is closed. Steps 1-6 ship together in 2.1.0.

## Releases

- 2.1: `watch` (detection, shared state, notification, restore, resume list), `accounts link`,
  `service install|uninstall|status`, `run` switching on a remote mark.
- 2.2: automatic resume through a scheduled task, after the check.
