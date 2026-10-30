# A limit after a switch belongs to the session's account (2.3.1)

Problem, seen on 2026-10-29: at 20:55 Claude Desktop switched from `great` to `genesis`. A Code-tab
session on an SSH host had been started under `great`. At 20:59 a background task notification
woke it, and its turn failed on `great`'s weekly limit ("resets Nov 3, 2pm"). `watch_pass()` gives
each limit error to `desktop_account_at(history, ts)`, the account Claude Desktop was signed in to
at that time. So it marked `genesis` as exhausted until `great`'s reset. `claude-relay run` then
skipped `genesis`, which was free. The session went into `pending` under `genesis`, so the move to
`genesis` left it out of `resume.json`.

What the cards showed (the backup `desktop` made at 21:07, before copying): the session's card was
only in `great`, last active at 20:51. A session started in `genesis` after the switch had its card
only in `genesis`. Claude Desktop updates only the card of the account it is signed in to.

## Plan

1. `card_versions()` reads every Code-tab card once per pass, and only when there is a new limit
   error. It returns `{cliSessionId: {account: card_version}}`.
2. `session_account()` gives the error to the account that holds the session's newest card. On a
   tie, or with no card, the error goes to the account Claude Desktop was signed in to at that time,
   as before. A session copied by an earlier move has the same card version in both accounts until
   it goes on in one of them.
3. A subagent's transcript (`agent-<id>.jsonl`) is not named after its session, but its lines
   carry the session's `sessionId` (checked on 2026-10-30). `scan_transcripts()` adds it to each
   event. When the file name matches no card, the card is looked up by that id.
4. `watch_pass()` uses that account for `pending`, the mark and the notification. Errors from
   before `watch` knew the account are still ignored.

## Acceptance

- After a switch from acctA to acctB, limit errors are attributed like this
  (`tests/test_watch.py`):
  - a session with its card only in acctA goes to acctA, and so does a subagent of that session;
  - a session with a newer card in acctA than in acctB goes to acctA;
  - a session with its card only in acctB goes to acctB;
  - a session with equal cards in both accounts goes to acctB.

## Left open

- A wrong mark made before 2.3.1 stays until `claude-relay reset NAME`.
- A session with no card on this Mac (a Code-tab card that was deleted) still goes to the account
  Claude Desktop was signed in to at that time.
