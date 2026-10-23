# claude-relay

- One Python file, `bin/claude-relay`, standard library only, Python 3.8+. English only.
- Tests: `python3 -m unittest discover -s tests -v`. They run the real CLI against a temporary HOME
  with fakes for `claude`, `ssh`, `pgrep`, `osascript`, `open` and `launchctl`.
- Release: bump `version` in `package.json` and `__version__` in `bin/claude-relay`, add a section to
  `CHANGELOG.md`, merge to `main`; the release workflow does the rest.
- No kanban: plans go in `docs/plans/`, PRs have no issue, and merges wait for the owner's go-ahead.
