# Changelog

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
