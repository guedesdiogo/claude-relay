#!/bin/sh
# Install claude-relay without Homebrew or npm (Linux servers, or macOS without Homebrew).
#
#   curl -fsSL https://raw.githubusercontent.com/guedesdiogo/claude-relay/main/install.sh | sh
#
# Options (environment variables):
#   CLAUDE_RELAY_VERSION=v2.0.0   install a specific release (default: latest release)
#   CLAUDE_RELAY_BIN_DIR=~/bin    where to put the commands (default: ~/.local/bin)
set -eu

REPO="guedesdiogo/claude-relay"
BIN_DIR="${CLAUDE_RELAY_BIN_DIR:-$HOME/.local/bin}"
VERSION="${CLAUDE_RELAY_VERSION:-}"

say() { printf '%s\n' "$*"; }
fail() { say "claude-relay install: $*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "python3 is required (3.8 or newer). Install it first."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
  || fail "python3 is too old; claude-relay needs 3.8 or newer."

if command -v curl >/dev/null 2>&1; then
  fetch() { curl -fsSL "$1"; }
elif command -v wget >/dev/null 2>&1; then
  fetch() { wget -qO- "$1"; }
else
  fail "curl or wget is required."
fi

if [ -z "$VERSION" ]; then
  VERSION=$(fetch "https://api.github.com/repos/$REPO/releases/latest" \
    | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1)
  [ -n "$VERSION" ] || VERSION="main"
fi

mkdir -p "$BIN_DIR"
for cmd in claude-relay claude-session-restorer; do
  tmp="$BIN_DIR/.$cmd.download"
  fetch "https://raw.githubusercontent.com/$REPO/$VERSION/bin/$cmd" > "$tmp" || fail "download of $cmd failed"
  head -n 1 "$tmp" | grep -q python3 || fail "unexpected content for $cmd"
  chmod 755 "$tmp"
  mv "$tmp" "$BIN_DIR/$cmd"
done

say "Installed claude-relay $VERSION in $BIN_DIR"
"$BIN_DIR/claude-relay" --version
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "Add $BIN_DIR to your PATH, for example: echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.profile" ;;
esac
say "Next: claude-relay accounts add <name>   (paste a token from: claude setup-token)"
