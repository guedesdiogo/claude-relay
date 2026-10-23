# The terminal follows Claude Desktop's account (2.2.0)

Goal: when the account changes, by hand or because of a usage limit, Claude Code in the terminal
(on the Mac and on the SSH hosts) moves to the same account as Claude Desktop.

## How

1. `watch` publishes which account Claude Desktop uses: every pass it writes the linked name
   (`accounts link`) as `desktop` in the state, on the Mac and on every `remote` host.
2. `claude-relay run` follows it (setting `follow_desktop`, default on):
   - a new run starts on the Desktop account when that account has a token and is available;
   - a running session switches at the end of the turn when the Desktop account changes, and
     resumes the same conversation there;
   - when the Desktop account is exhausted, the existing rule applies: another available account.
3. `claude-relay remote install HOST` copies claude-relay to `~/.local/bin` on the host and imports
   the Mac's account names and Desktop links. Tokens are not copied between machines (decided
   while building it: copying them is a write into another machine's secret store).

## What still needs the user

- Once per account per year: `claude setup-token` (browser), then `claude-relay accounts add NAME`
  on each machine where the terminal is used (the same token can be pasted on both).
- Start Claude in the terminal through claude-relay: `alias claude='claude-relay run'`.
- Plain `claude` started without claude-relay keeps its own `/login` account and cannot be switched.
