# claude-relay

[![CI](https://github.com/guedesdiogo/claude-relay/actions/workflows/ci.yml/badge.svg)](https://github.com/guedesdiogo/claude-relay/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Use several Claude subscriptions as one, without losing your sessions.**

- **In the terminal**, `claude-relay run` starts Claude Code with one of your accounts. When that
  account gets close to its usage limit, or hits it, claude-relay switches to the next account and
  resumes the **same session** on its own: you keep working where you were.
- **In Claude Desktop**, `claude-relay desktop` brings your Code-tab sessions along when you switch
  accounts, and restarts Claude Desktop's helpers on your SSH servers so remote sessions use the
  new account too.
- **In the background**, `claude-relay watch` notices when an account hits its limit, on your Mac
  and on your SSH servers, marks it everywhere, tells you to switch Claude Desktop, and moves your
  sessions as soon as you have. Signing Claude Desktop in is the only step left to you.

Everything stays in one conversation history: sessions are files on disk that belong to no
account, so you can go from account A to B and back as often as you like.

> Unofficial community tool, not affiliated with or endorsed by Anthropic.
> Anthropic staff have said publicly that holding several Max subscriptions is not against the
> terms, and there are also reports of multi-account users being flagged by automated abuse
> systems. Make sure your use fits Anthropic's terms and the rules of whoever pays for each
> subscription.

---

## Contents

- [Install](#install)
- [Terminal: automatic account failover](#terminal-automatic-account-failover)
- [Claude Desktop: switching accounts](#claude-desktop-switching-accounts)
- [Automatic switching: watch](#automatic-switching-watch)
- [SSH servers](#ssh-servers)
- [Commands](#commands)
- [Settings](#settings)
- [How it works](#how-it-works)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Upgrading from claude-session-restorer](#upgrading-from-claude-session-restorer)
- [Development](#development)
- [Credits and license](#credits-and-license)

---

## Install

Requirements: **Python 3.8+** and [Claude Code](https://code.claude.com). The `desktop` command
is for Claude Desktop on **macOS**; everything else also works on **Linux**.

### Homebrew (macOS, recommended)

```bash
brew install guedesdiogo/tap/claude-relay
```

### Script (Linux servers, or any machine without Homebrew)

```bash
curl -fsSL https://raw.githubusercontent.com/guedesdiogo/claude-relay/main/install.sh | sh
```

It installs into `~/.local/bin` (change with `CLAUDE_RELAY_BIN_DIR`).

### npm from GitHub Packages

GitHub Packages asks for a GitHub token even for public packages. Create a classic token with only
the `read:packages` scope at <https://github.com/settings/tokens/new>, then:

```bash
echo "@guedesdiogo:registry=https://npm.pkg.github.com" >> ~/.npmrc
echo "//npm.pkg.github.com/:_authToken=YOUR_GITHUB_TOKEN" >> ~/.npmrc
npm install -g @guedesdiogo/claude-relay
```

Check with `claude-relay --version`.

---

## Terminal: automatic account failover

### 1. Add your accounts (once)

For **each** subscription, create a long-lived token. Run this in a terminal on a computer with a
browser, and sign in to that account when the browser opens:

```bash
claude setup-token
```

It prints a token that starts with `sk-ant-oat01-` and is valid for one year. Store it:

```bash
claude-relay accounts add work      # paste the token when asked; it is not shown
claude-relay accounts add personal
claude-relay accounts list
```

On macOS tokens go into the **Keychain**; on Linux into `~/.config/claude-relay/tokens/` with
permissions `600`. The first account you add is the one used first.

### 2. Start Claude through claude-relay

```bash
claude-relay run                     # same as `claude`
claude-relay run --model opus "fix the failing test"
claude-relay run -c                  # any claude option works
```

To use it every time, add an alias to `~/.zshrc` or `~/.bashrc`:

```bash
alias claude='claude-relay run'
```

Subcommands such as `claude setup-token`, `claude mcp list` or `claude update`, and `--version` /
`--help`, go straight to plain `claude`. So does everything else while no account has a token yet.

The status line shows which account is in use and how much of it you have used:

```
⇄ work · 5h 42% · 7d 81%
```

If you already have a status line of your own, it is kept and this line is added under it.

### 3. What happens near the limit

| Situation | What claude-relay does |
| --------- | ---------------------- |
| The account reaches the **threshold** (95% of the 5-hour or weekly window by default) | Waits for the current reply to finish, then restarts Claude on the next account and resumes the same session. Nothing is interrupted. |
| The account **hits its limit** in the middle of a reply | Restarts on the next account, resumes the session and sends *"Continue exactly where you left off."* |
| An account's **token is rejected** (expired or revoked) | Same as above, and skips that account for a day. Fix it with `claude-relay accounts add <name>` again. |
| A **temporary** "capacity" error (429) | Nothing: that is not your account's limit. Claude retries as usual. |
| **No other account** is available | Leaves Claude running and shows *no other account available* in the status line. |

Accounts that reached the threshold or the limit are skipped until their window resets.
`claude-relay accounts list` shows when each one is available again.

Set the threshold with `claude-relay config threshold 90`. **`100` means "only switch when the
limit is actually hit"**.

Non-interactive runs work too: `claude-relay run -p "…"` continues on the next account with
`--resume` if the run stops on a usage limit.

---

## Claude Desktop: switching accounts

Claude Desktop keeps a separate session list per account, and its SSH helpers keep using the
account that started them. claude-relay cannot sign Claude Desktop in for you (there is no
supported way to do that), but it handles everything else.

**Every time you switch, in either direction:**

1. In Claude Desktop, sign out, sign in with the other account and open the **Code** tab once.
2. Run, in Terminal.app (not in a Code-tab session, which stops when the app quits):

   ```bash
   claude-relay desktop --existing-cards-only --quit --reopen
   ```

It quits Claude Desktop, copies the session list and the recurring scheduled tasks from your
other accounts into this one (and updates sessions you continued elsewhere), restarts Claude
Desktop's helpers on the SSH hosts you configured, and opens the app again. Your sessions are
there; continue any of them.

Useful shortcut:

```bash
alias claude-switch='claude-relay desktop --existing-cards-only --quit --reopen'
```

Leave out `--existing-cards-only` if you also want sessions you started from the `claude` CLI or
VS Code to appear in the app. Run `claude-relay desktop --dry-run` first to see how many that is.

**Scheduled tasks:** each account keeps its own list. Recurring tasks from your other accounts are
added to this one unless it already has a task with the same id; one-time tasks stay behind. A
change you make to a task (its schedule, turning it off) stays in the account where you made it,
and a task you delete in one account comes back from the others on the next switch, so delete it
in each account.

**What stays per account:** usage limits, one-time scheduled tasks, claude.ai connectors and cloud
sessions (Claude Code on the web). Archived status is per account too.

---

## Automatic switching: watch

`claude-relay watch` runs in the background on your Mac and does the switching work for you:

1. Every 30 s it reads new transcript lines on the Mac and, over SSH, on the hosts you added with
   `claude-relay remote add`. A Claude Desktop session that hits its usage limit leaves the reset
   time in its transcript.
2. It marks that account as exhausted until then, on the Mac and on every host, so
   `claude-relay run` skips it everywhere. A `claude-relay run` already on that account switches
   at the end of its current turn.
3. It sends a notification: *"work hit its weekly limit until Thu 22 Oct 17:00. Sign Claude Desktop
   in to home."*
4. When Claude Desktop is signed in to another account and no session has written for a minute, it
   quits the app, moves the sessions, restarts the helpers on your hosts and reopens the app.
5. It resumes the sessions that stopped on the limit. Before reopening the app, it lists them in
   `~/.config/claude-relay/resume.json` and registers a one-time Claude Desktop scheduled task,
   already due, so the app runs it as it opens. The task sends each session `resume_prompt`, 10 at a
   time. The first run may ask you to approve sending messages; allow it always. If the task cannot
   be added (the account's `scheduled-tasks.json` cannot be read, or a write fails), the
   notification says to resume the sessions by hand from `~/.config/claude-relay/resume.json`.
6. The terminal follows. Every pass, `watch` tells the Mac and every host which account Claude
   Desktop uses (its `accounts link` name). `claude-relay run` starts on that account, and a running
   session moves to it at the end of its current turn, resuming the same conversation. This holds
   whether you switched Claude Desktop by hand or because of a limit. If that account is exhausted
   or has no token on that machine, `run` uses another one. Turn this off with
   `claude-relay config follow_desktop false`.

**What you still do:**

| When | What |
| ---- | ---- |
| Each switch | Sign Claude Desktop in to the account the notification names, and open the Code tab. |
| Once per account | `claude-relay accounts link NAME ACCOUNT_ID` (ids from `claude-relay desktop --list`). |
| Once per account per year | `claude setup-token`, then `claude-relay accounts add NAME` on each machine where you use the terminal (the same token works on all of them). |
| Once | `claude-relay service install` (starts `watch` now and at every login). |
| Once per host | `claude-relay remote install HOST` (copies claude-relay and the account names there). |
| Once per machine | Start Claude through claude-relay: `alias claude='claude-relay run'` in your shell. |

```bash
claude-relay desktop --list                  # account ids
claude-relay accounts link work <id-1>       # name them
claude-relay accounts link home <id-2>
claude-relay accounts add work               # token from `claude setup-token`
claude-relay accounts add home
claude-relay remote add my-server
claude-relay remote install my-server        # then, on my-server: claude-relay accounts add work/home
claude-relay service install
claude-relay service status                  # running? last lines of the log
```

SSH hosts need nothing running, and `watch` needs nothing installed on them: the Mac sends the
script to `python3 -` over SSH. Install claude-relay on a host (`remote install`) to use
`claude-relay run` there. Tokens are never copied between machines.

A plain `claude` started without claude-relay keeps its own `/login` account and does not follow.

Errors from before `watch` started are ignored: it only knows which account they belong to from
the moment it sees Claude Desktop signed in. Rotating accounts automatically is exactly what
automated abuse systems look for; see the note at the top.

---

## SSH servers

There are two separate things, depending on how you use the server.

**You open Claude Code in a terminal on the server** (over SSH): install claude-relay **on the
server** with the script above, add your accounts there, and use `claude-relay run` as on your
Mac. Tokens are created on a computer with a browser (`claude setup-token`) and pasted into
`claude-relay accounts add` on the server.

**Claude Desktop runs sessions on the server** (sessions whose folder is on the server): Claude
Desktop starts a helper there with the credentials of the account that started it. Tell
claude-relay about the host once, on your Mac:

```bash
claude-relay remote add my-server    # a host name that works with plain `ssh my-server`
```

From then on, `claude-relay desktop` stops those helpers on each switch (Claude Desktop starts new
ones with the current account), and `claude-relay watch` keeps the host's exhausted accounts in
sync with the Mac. It needs key-based SSH login (no password prompt). Running sessions on that host
are interrupted, so let replies finish before switching (`watch` waits for that on its own).

---

## Commands

| Command | What it does |
| ------- | ------------ |
| `claude-relay run [claude options]` | Start Claude Code with automatic failover. |
| `claude-relay accounts add NAME` | Store the token for an account (`--token-file PATH` to read it from a file). |
| `claude-relay accounts list` / `status` | Accounts, recorded usage and availability. `*` marks the first choice. |
| `claude-relay accounts remove NAME` | Forget an account and delete its token. |
| `claude-relay accounts link NAME ACCOUNT_ID` | Name a Claude Desktop account, so `watch` marks and names it. |
| `claude-relay use NAME` | Make an account the first choice. |
| `claude-relay reset [NAME]` | Forget recorded usage, so skipped accounts are tried again. |
| `claude-relay config [KEY [VALUE]]` | Show or change settings. |
| `claude-relay remote add/remove/list HOST` | SSH hosts that `desktop` restarts and `watch` keeps in sync. |
| `claude-relay remote install HOST` | Copy claude-relay to `~/.local/bin` on the host, with the account names and Desktop links (not the tokens). |
| `claude-relay desktop [options]` | Move Code-tab sessions to the account Claude Desktop is signed into. |
| `claude-relay watch [--once] [--interval S]` | Follow usage limits and Claude Desktop account switches (see above). |
| `claude-relay service install/uninstall/status` | Run `watch` as a launchd agent (macOS). Log: `~/.config/claude-relay/watch.log`. |

`claude-relay desktop` options:

| Option | What it does |
| ------ | ------------ |
| `--list` | Account folders, how many sessions each has, which one is signed in. Changes nothing. |
| `--dry-run` | Show what would change without writing anything. |
| `--existing-cards-only` | Only sessions created in the Desktop Code tab (skip CLI / VS Code sessions). |
| `--quit` / `--reopen` | Quit Claude Desktop first / open it again when done. |
| `--remote HOST` / `--no-remotes` | Restart helpers on this host instead of the configured list / on none. |
| `--account UUID --org UUID` | Target this account instead of the detected one. |
| `--cards-dir`, `--projects-dir`, `--dest-root` | Other folders (testing or unusual setups). |
| `--ignore-running`, `--no-backup` | Testing only. |

---

## Settings

`claude-relay config` shows them; `claude-relay config KEY VALUE` changes one.

| Key | Default | Meaning |
| --- | ------- | ------- |
| `threshold` | `95` | Switch when the 5-hour or weekly window reaches this %. `100` = only when the limit is hit. |
| `continue_prompt` | `Continue exactly where you left off.` | Sent after a switch that interrupted a reply. |
| `cooldown_minutes` | `30` | How long to skip an account that hit its limit when its reset time is unknown. |
| `claude_bin` | `claude` | The Claude Code command to start. |
| `notify` | `true` | macOS notification when an account switch happens. |
| `follow_desktop` | `true` | `run` uses the account Claude Desktop uses (published by `watch`) and moves with it. |
| `resume_prompt` | *(see `config`)* | What `watch`'s resume task sends to each session that stopped on the limit. |

Files live in `~/.config/claude-relay/` (or `$XDG_CONFIG_HOME/claude-relay`, or
`$CLAUDE_RELAY_HOME`).

---

## How it works

**Terminal failover** uses documented Claude Code features only:

- Each account's token is passed to Claude Code in `CLAUDE_CODE_OAUTH_TOKEN`, which takes priority
  over the `/login` credentials. `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are removed for that
  process, because they would take priority over the token.
- claude-relay adds, for that session only (`--settings`, nothing is written to your settings
  files), a status line that records `rate_limits` (5-hour and weekly usage and reset times) and
  three hooks: `SessionStart` (session id), `Stop` (end of a reply) and `StopFailure` (a reply
  failed on `rate_limit`, `billing_error` or `authentication_failed`).
- When a switch is needed, claude-relay stops Claude, starts it again with the next account and
  `--resume <session id>`, keeping your other options. Conversations are files under
  `~/.claude/projects` that belong to no account, so the history is intact.
- In `-p` mode Claude can exit before a hook finishes, so claude-relay also reads the failure from
  the session transcript.

**Claude Desktop** does not list transcripts directly. It keeps a small "card" per session, per
account, in
`~/Library/Application Support/Claude/claude-code-sessions/<accountId>/<orgId>/local_*.json`, each
pointing at a transcript through `cliSessionId`. `claude-relay desktop` reads the signed-in
account from Claude Desktop's own config (`lastKnownAccountUuid`; Claude Desktop does not update
`~/.claude.json`), backs up the card folder, copies cards from other accounts, updates cards whose
copy elsewhere has newer activity, and optionally creates cards for CLI / VS Code transcripts. It
also adds the other accounts' recurring scheduled tasks to `scheduled-tasks.json` in the same
folder, without the record of their last run there; the task prompts live in
`~/.claude/scheduled-tasks/<id>/SKILL.md` and are shared by all accounts.
Remote helpers live in `~/.claude/remote/` on each SSH host.

**`watch`** looks for turns that failed on the usage limit: transcript entries with
`"entrypoint": "claude-desktop"`, `"error": "rate_limit"` and `"quotaLimits": {"status": "rejected",
"resetsAt": …}` (verified with Claude Code 2.1.299). Temporary capacity errors are ignored, and so
are terminal sessions, which `claude-relay run` already handles. Each error belongs to the account
Claude Desktop was signed in to at that moment. Marks are merged between machines (the later
reset wins).

The Claude Desktop file format was worked out by observation and may change in any app update.

---

## Security

- Tokens are stored in the macOS Keychain (service `claude-relay`) or in files readable only by
  you. claude-relay only ever hands them to the Claude Code process it starts, through its
  environment.
- `claude-relay accounts add` hides the token while you paste it, and on macOS the token is passed
  to the Keychain through standard input, so it never shows up in the process list.
- A token from `claude setup-token` can only make model requests and lasts one year. If one leaks,
  revoke it from your Claude account settings and run `claude-relay accounts remove`.
- `claude-relay desktop` backs up the whole card folder before writing and never modifies or
  deletes transcripts. Undo: quit Claude Desktop, replace `claude-code-sessions` with the backup
  folder `claude-code-sessions_backup_<date>_<time>`, reopen.

Claude Code deletes transcripts older than 30 days by default. To keep sessions longer, put this in
`~/.claude/settings.json` on each machine:

```json
{ "cleanupPeriodDays": 3650 }
```

---

## Troubleshooting

**Claude still says the limit was reached after a Desktop switch** — Sessions that run on an SSH
host use Claude Desktop's helper there. Add the host with `claude-relay remote add <host>` and run
`claude-relay desktop` again, or on the host run
`pkill -u "$USER" -f "$HOME/.claude/remote/(srv|ccd-cli)/"` with Claude Desktop closed.

**"Claude Desktop is still running"** — The app rewrites its session list when it exits. Use
`--quit`, or quit with **Cmd+Q** (closing the window only hides it).

**"Could not check whether Claude Desktop is running"** — `pgrep` is missing or failed, so
`desktop` cannot tell if the app is open and copies nothing. Quit Claude Desktop with **Cmd+Q**,
then run again with `--ignore-running` (without `--quit`).

**"… has no session folder yet. Open the Code tab …"** — Claude Desktop creates the folder for an
account the first time you open the Code tab with it.

**The plain `claude` command uses the wrong account** — Claude Desktop and the `claude` command
have separate logins. Use `claude-relay run`, or `/login` inside `claude`.
`claude-relay desktop` prints a note when they differ.

**An account is skipped although it has usage left** — `claude-relay accounts list` shows why and
until when. `claude-relay reset NAME` makes claude-relay try it again.

**No usage shown for an account** — Usage comes from Claude Code's status line, which only
receives it for Pro and Max subscriptions and only after the first reply.

---

## Upgrading from claude-session-restorer

This project used to be called `claude-session-restorer`. `brew upgrade` moves you to
`claude-relay` automatically, and the old command keeps working: `claude-session-restorer [options]`
runs `claude-relay desktop [options]`. Old links to the repository redirect here.

---

## Development

```bash
git clone https://github.com/guedesdiogo/claude-relay.git
cd claude-relay
python3 -m unittest discover -s tests -v
```

The tests run the real CLI against a temporary home folder and a fake `claude`
(`tests/fake_claude.py`) that calls the status line and hooks the way Claude Code does. They never
touch your real Claude data.

**Releasing:** bump `version` in `package.json` and `__version__` in `bin/claude-relay`, add a
`## x.y.z` section to `CHANGELOG.md`, and push to `main`. The
[release workflow](.github/workflows/release.yml) runs the tests, creates the tag and the GitHub
Release, publishes the npm package to GitHub Packages and renders the Homebrew formula. With a
`HOMEBREW_TAP_TOKEN` secret (a fine-grained token with Contents read/write on
`guedesdiogo/homebrew-tap`), it also updates the tap.

---

## Credits and license

- The Claude Desktop session list format and the original Windows tool:
  [sahol3/claude-code-session-restorer](https://github.com/sahol3/claude-code-session-restorer).
- claude-relay: [Diogo Guedes](https://github.com/guedesdiogo).

[MIT](LICENSE).
