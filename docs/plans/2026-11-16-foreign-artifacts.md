# Say which artifacts belong to another account (2.3.2)

Problem, seen up to 2026-11-16: after an account switch, Code-tab sessions that had published
artifacts could no longer use them. The Artifact tool answered "artifact not found — … it has not
been shared with you" on a read, and "the artifact you're updating was deleted, or you no longer have
write access to it. This session has dropped its link to that Artifact" on a publish. Then the
session republished to a new URL or went on without the page.

What the files showed:

- Each card keeps the session's artifacts in `publishedArtifacts`
  (`[{url, title, sourcePath, updatedAt}]`). `desktop` already copies them with the card. 47
  sessions with artifacts had the same list in every account, and the 3 that differed were older
  copies in an account not switched to since.
- An artifact lives on claude.ai, in the account that published it, and is private by default.
  Two failures checked against `watch`'s history: `DCYuPBej…` was published under `genesis` and
  failed under `diogoaguedes`; `8Gkpueg…` was published under `diogoaguedes` and failed under
  `great`. In both cases the account Claude Desktop was signed in to at the entry's `updatedAt` was
  the publishing one.
- claude-relay cannot move or share an artifact. Its tokens only make model requests, and
  claude.ai has no supported way for it to share a page. The Artifact tool has no sharing option
  either.

## Plan

1. After copying the cards, `desktop` looks at this account's open (not archived) cards. That
   includes the cards it would copy or update in a dry run.
2. Each `publishedArtifacts` entry belongs to the account Claude Desktop was signed in to at its
   `updatedAt`, taken from `watch`'s history (`desktop_account_at`). Entries from before that history
   starts, or with no `updatedAt`, are left out: their account is unknown.
3. When some entries belong to another account, `desktop` says how many and in how many sessions.
   It says that this account cannot open or update them, and how to fix that: share each one with
   this account on claude.ai, or continue the session in the account that owns it. Then it lists
   them, grouped by owner (the `accounts link` name): the session title, the artifact title and the URL.
4. README: artifacts go under "What stays per account", with the same two remedies.

## Acceptance

- `tests/test_desktop.py`. `watch` history: acctA signed in at 1000 s, acctB at 2000 s. acctB's
  `desktop` lists the artifact a session published at 1500 s, under acctA's linked name, and says
  the count. It leaves out an artifact updated at 2500 s, which is acctB's own; one in an archived
  session; and one from before the history starts.
- With no `watch` history, `desktop` prints nothing about artifacts.
- A dry run lists the artifacts of the cards it would copy.

## Left open

- `watch` keeps the last 20 switches, so older artifacts end up with no known owner and are not listed.
- If `watch` moves the sessions in the same pass that first sees the new account, history does not
  have that switch yet. An artifact published in the new account up to 30 s earlier would count as
  the previous account's.
- The `watch` notification does not mention these artifacts. `watch.log` has `desktop`'s output.
