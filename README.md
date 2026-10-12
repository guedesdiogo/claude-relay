# claude-session-restorer

[![CI](https://github.com/guedesdiogo/claude-session-restorer/actions/workflows/ci.yml/badge.svg)](https://github.com/guedesdiogo/claude-session-restorer/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Switch between Claude accounts on your Mac without losing your Claude Code sessions.**

When you log into a different Claude account in Claude Desktop, the **Code** tab shows an empty
session list. Your conversations are not gone — the app just keeps a separate session list per
account. `claude-session-restorer` rebuilds that list for whichever account you are logged into,
so you can pick up any session exactly where you left off. Switch back, run it again, and you are
back where you were. Repeat as often as you like.

> This is a macOS port of
> [sahol3/claude-code-session-restorer](https://github.com/sahol3/claude-code-session-restorer)
> (Windows / PowerShell). It is an unofficial community tool, not affiliated with or endorsed by
> Anthropic.

---

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Switching between two accounts, as often as you need](#switching-between-two-accounts-as-often-as-you-need)
- [Options](#options)
- [How it works](#how-it-works)
- [Safety, backups and undo](#safety-backups-and-undo)
- [Troubleshooting](#troubleshooting)
- [Resuming from the terminal instead](#resuming-from-the-terminal-instead)
- [Development](#development)
- [Credits and license](#credits-and-license)

---

## Install

Requirements: **macOS** and **Python 3.8+**. If you use Homebrew you already have Python, because
Homebrew requires Apple's Command Line Tools, which include `python3`. Check with
`python3 --version`; if it is missing, run `xcode-select --install`.

### Option 1 — Homebrew (recommended)

```bash
brew install guedesdiogo/tap/claude-session-restorer
```

Update later with `brew upgrade claude-session-restorer`.

### Option 2 — npm from GitHub Packages

GitHub Packages requires a GitHub token to install **any** npm package, even public ones. One-time
setup:

1. Create a **classic** personal access token at
   <https://github.com/settings/tokens/new> with only the **`read:packages`** scope.
2. Tell npm where to find the `@guedesdiogo` scope and how to authenticate:

   ```bash
   echo "@guedesdiogo:registry=https://npm.pkg.github.com" >> ~/.npmrc
   echo "//npm.pkg.github.com/:_authToken=YOUR_TOKEN_HERE" >> ~/.npmrc
   ```

3. Install:

   ```bash
   npm install -g @guedesdiogo/claude-session-restorer
   ```

The npm package is a thin wrapper around the same Python script, so Python 3 is still required.

### Option 3 — just the script

```bash
curl -fsSLo /usr/local/bin/claude-session-restorer \
  https://raw.githubusercontent.com/guedesdiogo/claude-session-restorer/main/bin/claude-session-restorer
chmod +x /usr/local/bin/claude-session-restorer
```

(Use `sudo` if `/usr/local/bin` is not writable, or pick any folder on your `PATH`.)

Check the install:

```bash
claude-session-restorer --version
```

---

## Quick start

1. In **Claude Desktop**, sign out and sign in with the account you want to use. Open the **Code**
   tab once (it will look empty — that is expected).
2. Run:

   ```bash
   claude-session-restorer --quit --reopen
   ```

   This quits Claude Desktop, restores the session list for the logged-in account and opens the
   app again.
3. Go to the **Code** tab. Your sessions are listed; click one and continue.

Prefer to do it by hand? Quit Claude with **Cmd+Q** (closing the window is not enough), run
`claude-session-restorer`, then open Claude again.

---

## Switching between two accounts, as often as you need

The routine is the same in both directions:

| Step | Account A → Account B | Account B → Account A |
| ---- | --------------------- | --------------------- |
| 1 | Sign out of A, sign in with B, open the Code tab | Sign out of B, sign in with A, open the Code tab |
| 2 | `claude-session-restorer --quit --reopen` | `claude-session-restorer --quit --reopen` |
| 3 | Continue any session in B | Continue any session in A, including the progress you made in B |

Why it works in both directions:

- Every session is stored once on disk as a transcript that belongs to no account. When you
  continue a session in account B, the new messages go into that same transcript.
- When you go back to A, A's entry for the session still points at that transcript, so you see
  everything you did in B.
- Sessions you started in B are copied into A on the next run.
- Running the tool again never creates duplicates.

Things to avoid:

- **Do not use the same session from two accounts at the same time** (for example one in Claude
  Desktop and one in the terminal). Both would write to the same transcript.
- **Let Claude finish its current reply before switching**, so the transcript is not left
  mid-write.

Optional shell shortcut (add to `~/.zshrc`):

```bash
alias claude-switch='claude-session-restorer --quit --reopen'
```

---

## Options

| Option | What it does |
| ------ | ------------ |
| `--list` | Show every account folder, how many sessions it has and which one is logged in. Changes nothing. |
| `--dry-run` | Show what would be copied or created, without writing anything. |
| `--quit` | Quit Claude Desktop before restoring (waits until it has fully exited). |
| `--reopen` | Open Claude Desktop again when finished. |
| `--existing-cards-only` | Only move sessions that were created in the Desktop Code tab. Skips sessions started from the `claude` CLI or VS Code, to keep the list short. |
| `--account UUID --org UUID` | Restore into this account instead of the one detected from `~/.claude.json`. |
| `--cards-dir PATH` | Use a different Claude Desktop card folder. |
| `--projects-dir PATH` | Use a different Claude Code transcripts folder. |
| `--dest-root PATH` | Write cards to a scratch folder instead of the live one (testing). |
| `--ignore-running` | Do not stop if Claude Desktop seems to be running. Not recommended. |
| `--no-backup` | Skip the backup. Testing only. |
| `--version` | Print the version. |

---

## How it works

Claude Code stores each conversation as a transcript:

```
~/.claude/projects/<encoded-project-folder>/<sessionId>.jsonl
```

Transcripts are keyed by project folder and contain **no account information**, so switching
accounts never touches them.

The Claude Desktop **Code** tab does not read transcripts directly. It reads one small "card" per
session, stored **per account**:

```
~/Library/Application Support/Claude/claude-code-sessions/<accountId>/<organizationId>/local_*.json
```

Each card points at its transcript through a `cliSessionId` field. Cards have no account field;
they belong to an account only because of the folder they sit in. That is why sessions from
another account, and sessions started from the CLI or VS Code, do not show up.

On each run, the tool:

1. Reads the logged-in account from `~/.claude.json` (`oauthAccount.accountUuid` and
   `oauthAccount.organizationUuid`).
2. Backs up the whole `claude-code-sessions` folder.
3. Copies any card from another account folder whose transcript is not already listed for the
   current account.
4. Creates a card for every transcript that still has none, using the session title Claude
   generated (`aiTitle`), a summary, or the first user message, in that order.

---

## Safety, backups and undo

- **Backups:** before writing, the whole card folder is copied to
  `~/Library/Application Support/Claude/claude-code-sessions_backup_<date>_<time>`.
- **Add-only:** cards are only added. Transcripts are never modified or deleted.
- **Idempotent:** running it again skips everything already present.
- **Undo:** quit Claude, delete `claude-code-sessions`, rename the backup you want back to
  `claude-code-sessions`, and open Claude.

Backups accumulate over time. Delete old ones when you no longer need them:

```bash
ls -d ~/Library/Application\ Support/Claude/claude-code-sessions_backup_*
```

### Keep transcripts for longer

Claude Code deletes transcripts older than `cleanupPeriodDays` (30 days by default). To keep them
longer, add this to `~/.claude/settings.json`:

```json
{ "cleanupPeriodDays": 3650 }
```

It is also worth keeping a copy of your transcripts:

```bash
cp -R ~/.claude/projects ~/claude-projects-backup-$(date +%Y%m%d)
```

---

## Troubleshooting

**"Claude Desktop is still running"** — The app rewrites the card folder when it exits, so it has
to be closed first. Use `--quit`, or quit with **Cmd+Q** (closing the window only hides it).

**"Could not read the logged-in account"** — Sign in to Claude Desktop and open the Code tab once,
so `~/.claude.json` records the account. Then run again. You can also pass `--account` and
`--org`; get the IDs from `claude-session-restorer --list`.

**The detected account is the old one** — Open Claude Desktop, go to the Code tab with the new
account, quit with Cmd+Q, and run again. Confirm with `--list`.

**"… does not exist" for the card folder** — Claude Desktop may store cards somewhere else on your
version. Look with `ls ~/Library/Application\ Support/Claude/` and pass the right folder with
`--cards-dir`. Please [open an issue](https://github.com/guedesdiogo/claude-session-restorer/issues)
so the default can be fixed.

**Sessions still do not appear** — Run `claude-session-restorer --list` and check that the
logged-in account folder has cards. A Claude Desktop update may have changed the file format;
please open an issue with your Claude Desktop version.

**Cloud sessions** — Sessions that ran in the cloud (Claude Code on the web or remote sessions)
belong to the account that created them and cannot be moved by this tool.

---

## Resuming from the terminal instead

You do not need this tool if you are happy to resume from the command line. From the project
folder:

```bash
claude --continue          # most recent session in this folder
claude --resume            # choose from a list
claude --resume <sessionId>
```

The list is scoped to the current folder, not to the account.

---

## Development

```bash
git clone https://github.com/guedesdiogo/claude-session-restorer.git
cd claude-session-restorer
python3 -m unittest discover -s tests -v
```

The tests run the real CLI against a temporary fake home folder; they never touch your real
Claude data.

**Releasing:** bump the version in `package.json` and in `__version__` inside
`bin/claude-session-restorer`, add a `## 1.2.3` section to `CHANGELOG.md`, and push to `main`.

When the version on `main` has no matching tag yet, the
[release workflow](.github/workflows/release.yml) runs the tests, creates the tag and the GitHub
Release (notes taken from `CHANGELOG.md`),
publishes the npm package to GitHub Packages and, if the `HOMEBREW_TAP_TOKEN` secret is set,
updates the formula in [guedesdiogo/homebrew-tap](https://github.com/guedesdiogo/homebrew-tap).
That secret is a fine-grained token with **Contents: read and write** on the tap repository.

---

## Credits and license

- Original Windows tool and research into the card format:
  [sahol3/claude-code-session-restorer](https://github.com/sahol3/claude-code-session-restorer).
- macOS port, packaging and extra options: [Diogo Guedes](https://github.com/guedesdiogo).

[MIT](LICENSE). The file format was worked out by observation and may change in any Claude Desktop
update. The tool backs up before writing and only adds files, but you use it at your own risk.
