# A cleared mark stays cleared on every machine (2.2.2)

Problem (measured on 2.2.1): `watch` merges the `exhausted` marks of the Mac and the SSH hosts with
"the later reset wins". `claude-relay reset NAME` (or `use NAME`) removes the mark only where it
runs, and the next pass brings it back from the other machine. A new token from `accounts add NAME`
does not lift a "token rejected" mark either, so the account stays skipped for a day everywhere.

## How

1. Every new mark records `since`, when it was created:
   - `run` (a turn that failed on the account): the time of the failure;
   - `watch` (a Claude Desktop limit in a transcript): the time of that transcript entry.

   Marks from older versions have no `since` and count as older than any clear.
2. The state gets `cleared: {NAME: epoch}`, the last time the owner cleared that account's mark:
   - `reset NAME`, or every account with plain `reset`;
   - `use NAME`;
   - `accounts add NAME`, when the mark is "token rejected". A new token does not lift a usage
     limit, so other marks stay.
3. The merge used by `watch` and by `_sync` on the hosts:
   - `cleared` is merged first, and the later time per account wins;
   - marks whose `since` is not after that account's `cleared` are dropped, on both sides;
   - among the marks left, the later reset still wins.

   `watch` sends `cleared` to every host and reads it back, so a clear made on either side wins
   everywhere on the next pass.
4. `watch` skips a limit error from before the account's clear, so it does not notify about it again.

## Not changed

- `account_block` still reads only `exhausted`; the merge keeps cleared marks out of the state.
- Hosts with an older `claude-relay` installed keep working. Their `run` writes marks without
  `since`, and a later clear drops those marks. Run `claude-relay remote install HOST` again after
  upgrading.

## Also in 2.2.2

- A `reset` that runs during a `watch` pass is no longer undone. The pass ends by merging against
  the state as it is then, and it respects the new `cleared` time.
- `accounts add` joins a token pasted over several lines (`parse_token_text`). It took only the
  first line, so a token copied from a narrow terminal was saved cut short and then rejected.
