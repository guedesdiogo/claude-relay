# Sessions the account already had follow the other account (2.3.0)

Problem (measured on 2.2.1, after a switch from great to genesis with 330 cards each, 325 of them
in both accounts):

- **Archive.** 57 cards are archived in one account and open in the other: 56 archived in great,
  1 in genesis, with the same `lastActivityAt`. Archiving changes no timestamp, and `sync_card`
  only runs when `lastActivityAt` is newer, so the archive never carried over. Sessions archived in
  one account came back open after the switch.
- **Continued sessions.** In 47 pairs the session went on in great (more turns, newer
  `latestUserFrameAt`, other `lastAssistantUuid`, `postTurnSummary`, `prs`, `branch`, `error`).
  `sync_card` copied only `lastActivityAt`, `title` and `titleSource`, so genesis kept the old
  summary, PRs and error state. The pairs now share `lastActivityAt`, so a comparison on it alone
  no longer sees them.
- **New transcript.** Cards are matched by `cliSessionId` only. When Claude Desktop moves a card
  to a new transcript (`priorCliSessionIds`), the other account's copy does not match and is
  copied in as a second card next to the stale one (file name taken, so `local_<uuid>.json`). The
  code has this path, but the current data has no pair like that.

`completedTurns` cannot order copies: in 7 pairs the copy with more turns is the older one.

## How

1. Match a source card to the destination by `sessionId` (the file name, the same in every
   account), then by `cliSessionId`.
2. Order copies by `(lastActivityAt, latestUserFrameAt)`, with a missing value counting as 0.
3. A newer source copy replaces the destination card whole, keeping the destination's
   `sessionId`. Merging fields would keep stale ones (`error`, `errorAt`) that the newer copy no
   longer has. New cards are already copied verbatim.
4. When the copies are equally recent and only the source is archived, archive the destination.
   A newer destination is kept as it is, archived source or not: the session went on after the
   archive.
5. A replaced card's new `cliSessionId` counts as having a card, so the transcript scan does not
   add one for it.
6. `archived-sessions.idx` (`{"v":1,"archived":[sessionId, ...]}`, sorted) matches the cards'
   `isArchived` exactly in both accounts (genesis 221, great 280). The 89 archived cards that
   2.2.1 copied at 17:34 without touching the index were all in it after Claude Desktop reopened,
   so the app adds entries from the cards; removal was not observed. The sync adds and removes
   the ids of the cards it writes, and leaves a missing or unreadable index alone. On a copy of the
   real folder, the index after the run equals the archived cards (278 and 278).
7. Deleting a session leaves `deleted_<uuid>` for its sessionId and `deleted_<cliSessionId>` (the
   2026-10-12 backup has the card for one such pair; both markers have the same timestamp). Both
   ids count as present in the destination, so the copy and the transcript scan skip them. None of
   today's 5 markers has a card in another account.

Dry run on the real cards (genesis signed in): `updated 47 from a newer copy; archived 22 archived
in another account`. All 56 cards archived in great end up archived, 34 of them through the newer
copy. The 2 cards archived only in genesis stay archived, because genesis has the newer copy.

## Not changed

- A deletion does not carry over: a session deleted in one account stays in the others.

- No ledger of past syncs. With equally recent copies the archived one wins, so a session
  unarchived without new activity is archived again from the other account (README, "What stays
  per account").
- `watch` still moves sessions only when the signed-in account changes. The account signed in when
  2.3.0 is installed is fixed by running `desktop` once (CHANGELOG).
