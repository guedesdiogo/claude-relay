# Changelog

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
