# Changelog

## 2.3.0 — 2026-10-23

- `claude-relay desktop` (and `watch` when it moves the sessions) now brings the sessions this
  account already had up to date. Before, it only copied their last-activity time and title.
  - **A session continued in another account takes that account's card whole:** summary, branch,
    pull requests, error state, turns. Before, the rest of the card stayed as it was when you left.
    Cards that earlier versions updated only in part are fixed as well. They share
    `lastActivityAt` with the other copy, so `latestUserFrameAt` decides which copy is newer.
  - **A session archived in another account is archived here** when neither copy has newer
    activity. Archiving changes no timestamp, so before the archive never carried over, and
    archived sessions came back on every switch.
  - **A card is matched by its `sessionId`** as well as its `cliSessionId`. When Claude Desktop
    had moved a session to a new transcript, the switch added a second card for it next to the old
    one. Now it replaces the old card.
  - The summary line says how many cards each rule changed: `updated N from a newer copy;
    archived N archived in another account`.
  - The account's `archived-sessions.idx`, the sorted list of archived cards that Claude Desktop
    keeps next to them, is updated with the cards written: archived ones are added, and cards that a
    newer copy left open are removed. A missing or unreadable index is left alone.
- A session deleted in this account is no longer copied back from another account. Claude Desktop
  leaves `deleted_<sessionId uuid>` and `deleted_<cliSessionId>` behind. The card copy and the
  transcript scan now skip both ids.
- A copy with newer activity always wins, so a session you continued after archiving it stays
  open. A session you unarchive without continuing it is archived again from the other account.
- After upgrading, fix the account Claude Desktop is signed in to now. `watch` moves sessions only
  when the account changes. Quit Claude Desktop (Cmd+Q) and run in Terminal.app:
  `claude-relay desktop --existing-cards-only --reopen`.

## 2.2.4 — 2026-10-23

- When `watch` cannot add the task that resumes the sessions stopped on a limit, its macOS
  notification now says so: `Sessions moved to X; N session(s) stopped on the limit. Resume them by
  hand: the list is in <resume.json>.` Until now only `watch.log` said that they would not resume.

## 2.2.3 — 2026-10-23

- The one-time task that `watch` registers to resume sessions stopped on a limit no longer widens
  the account's `scheduled-tasks.json` to 0644; it stays 0600, as Claude Desktop keeps it.
- When that file cannot be read (not JSON, or `scheduledTasks` is not a list), `watch` leaves it
  as it is and says the resume task was not added, instead of replacing it and erasing the
  account's scheduled tasks. Resume the sessions in `resume.json` by hand in that case.

## 2.2.2 — 2026-10-23

- `claude-relay reset NAME` and `use NAME` now clear an exhausted mark on every machine. Before,
  `watch` brought the mark back from the other machine on its next pass, 30 s later. Each mark
  now records when it was made (`since`). Each machine records when each account's mark was last
  cleared (`cleared`), and `watch` and the SSH hosts exchange these times. A mark older than the
  account's last clear is dropped everywhere. A limit hit after the clear marks the account again.
  A plain `reset` clears every configured account. This also fixes a `reset` that ran during a
  `watch` pass: the end of the pass wrote the mark back.
- `claude-relay accounts add NAME` reads a token pasted over several lines. A token copied from a
  narrow terminal arrives broken into lines. Before, only the first line was saved (51 or 73 of
  108 characters), and Claude rejected the token. The lines after `sk-ant-...` that hold only
  token characters are now joined back to it, without the spaces around them.
  - This applies to all three ways in: the hidden prompt, a pipe (`pbpaste | claude-relay
    accounts add NAME`) and `--token-file`.
  - The prompt no longer uses getpass, which returned only the first line and left the rest for
    the shell to run as commands. It reads the lines that arrive within 0.2 s, still hidden, and
    discards anything after them.
  - `accounts add` refuses a token that does not start with `sk-ant-` or is shorter than 100
    characters, and asks for the whole token. Before, it saved the piece.
- `claude-relay accounts add NAME` clears a "token rejected" mark for that account the same way.
  Before, the account stayed skipped for a day on every machine, even after its new token was
  saved. Usage-limit marks stay: a new token does not reset the limit.
- After upgrading, take two steps:
  - Run `claude-relay service install` to restart `watch`. The running agent keeps the old version
    in memory, and it is the agent that sends the merge code to the hosts.
  - Run `claude-relay remote install HOST` again. Until then, `run` on the host still writes marks
    without `since`, and the next clear of that account drops them.

## 2.2.1 — 2026-10-23

- `claude-relay run` works as a drop-in for `claude` behind `alias claude='claude-relay run'`:
  Claude Code subcommands (`setup-token`, `mcp`, `update`, `doctor`, `plugin`, `auth`...) and
  `--version` / `--help` go straight to plain `claude`. Before, `claude setup-token` failed with
  "unknown option '--settings'".
- While no account has a token, `run` starts plain `claude` with a note instead of exiting with an
  error, so the alias can go in before the first `accounts add`.

## 2.2.0 — 2026-10-23

- The terminal follows Claude Desktop: every pass, `watch` publishes the account Claude Desktop
  uses (its `accounts link` name) on the Mac and on the `remote` hosts. `claude-relay run` starts on
  it and a running session moves to it at the end of the turn, whether Claude Desktop switched by
  hand or because of a limit. Exhausted accounts and accounts without a token on that machine are
  skipped. New setting `follow_desktop` (default on).
- New `claude-relay remote install HOST`: copies claude-relay to `~/.local/bin` on the host with the
  account names and Desktop links. Tokens are not copied; add them on the host with `accounts add`.

## 2.1.1 — 2026-10-23

- `claude-relay desktop` (and so `watch`) also brings Claude Desktop's recurring scheduled tasks
  to the account the app is signed in to. Each account registers its own tasks, so before a
  switch left them behind and they stopped running. Tasks the account already has, by id, stay
  as they are; one-time tasks and the record of a task's last run in the other account are not
  copied. `--dry-run` shows how many would be copied, and the backup covers the task lists.

## 2.1.0 — 2026-10-23

- New `claude-relay watch`: every 30 s it reads new transcript lines on the Mac and, over SSH, on
  the `remote` hosts (the script is piped to `python3 -`, so hosts need nothing installed). When a
  Claude Desktop session hits its usage limit it marks the account exhausted until the reset time
  from the transcript (`quotaLimits.resetsAt`), on every machine, and sends a notification naming
  the next account to sign in to. Once Claude Desktop is signed in to another account and no
  session has written for a minute, it quits the app, moves the sessions, restarts the hosts'
  helpers and reopens the app. The sessions that stopped on the limit are listed in `resume.json`
  and resumed by a one-time Claude Desktop scheduled task that `watch` registers, already due,
  before reopening the app (message: new setting `resume_prompt`).
- New `claude-relay service install | uninstall | status`: runs `watch` as a launchd agent.
- New `claude-relay accounts link NAME ACCOUNT_ID`: names a Claude Desktop account, so `watch`
  marks the claude-relay account of the same name.
- `claude-relay run` switches at the end of the turn when its account is marked exhausted by
  `watch` or by another machine.

## 2.0.2 — 2026-10-17

- `claude-relay desktop` no longer copies sessions when it cannot check whether Claude Desktop is
  running. Before, a missing `pgrep` or a `pgrep` error counted as "not running", so the "still
  running" check passed and `--quit` reported success with the app possibly open. It now stops,
  says why, and asks you to quit the app with Cmd+Q and run again with `--ignore-running`.

## 2.0.1 — 2026-10-17

- `claude-relay desktop` now sees Claude Desktop when it runs from a terminal the app started (a
  Code-tab session). On macOS, `pgrep` leaves out its own ancestors unless given `-a`, so `--quit`
  quit nothing and the "still running" check passed with the app open.
- `--quit` warns when it runs inside Claude Desktop: quitting the app most likely stops the command
  before it copies anything. Run it from Terminal.app.

## 2.0.0 — 2026-10-12

The project is now **claude-relay**: it uses several Claude subscriptions as one.

- New `claude-relay run`: starts Claude Code with one of your accounts and, when it reaches the
  usage threshold (default 95% of the 5-hour or weekly window, configurable; 100 = only on the
  limit) or hits its limit, switches to the next account and resumes the same session with
  `--resume`. Works in interactive and `-p` mode. Verified against Claude Code 2.1.296.
- New `claude-relay accounts add | list | remove`, `use`, `reset` and `config`. Tokens from
  `claude setup-token` are kept in the macOS Keychain or in 0600 files on Linux.
- `claude-relay desktop` (formerly `claude-session-restorer`): also restarts Claude Desktop's
  helpers on configured SSH hosts (`claude-relay remote add <host>`), so remote sessions use the new
  account, and updates cards whose copy in another account has newer activity.
- `claude-relay desktop` warns when the `claude` command is signed into a different account than
  Claude Desktop.
- Linux support for everything except `desktop`, with an `install.sh` installer.
- `claude-session-restorer` keeps working and forwards to `claude-relay desktop`.
- Renamed: repository `guedesdiogo/claude-relay`, Homebrew formula `claude-relay`, npm package
  `@guedesdiogo/claude-relay`.

## 1.1.0 — 2026-10-12

- Detect the account Claude Desktop is signed into from its own config (`lastKnownAccountUuid`).
  Claude Desktop does not update `~/.claude.json` when you switch accounts in the app, so 1.0.x
  restored into the previous account. `~/.claude.json` is now only a fallback.
- Clear message when the new account has no session folder yet (open the Code tab once).
- `--list` and the restore output say where the account was detected from.

## 1.0.1 — 2026-10-12

- `--dry-run` no longer requires Claude Desktop to be closed, since it writes nothing.

## 1.0.0 — 2026-10-12

First release. macOS port of
[`restore-code-tab-sessions.ps1`](https://github.com/sahol3/claude-code-session-restorer).

- Copies Code-tab session cards from other Claude accounts into the logged-in account.
- Creates cards for CLI / VS Code transcripts that have none, titled from the transcript.
- Backs up the card folder before every run; never touches transcripts; safe to run repeatedly.
- New compared with the original: `--list`, `--dry-run`, `--quit`, `--reopen`,
  `--cards-dir`, `--projects-dir`, `--version`.
- Fixed: two runs within the same second no longer fail on a backup-folder name collision.
- Distributed through Homebrew (`guedesdiogo/tap`) and npm on GitHub Packages.
