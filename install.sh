#!/usr/bin/env bash
# Wonder in the Margin — installer.
#
#   ./install.sh              install/refresh the Muse plugin + put
#                             `muse-margin` (and `muse-margintop`) on your PATH
#   ./install.sh --with-muse-shim
#                             also link a `muse` shim so `muse --margin side`
#                             works (requires the shim dir before the real
#                             muse on PATH — the installer only prints how)
#
# Nothing here touches the real `muse` binary.
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-${HOME:-}/.local/bin}"
WITH_SHIM=0
[ "${1:-}" = "--with-muse-shim" ] && WITH_SHIM=1

say() { printf '│ %s\n' "$*"; }
die() { printf '│ ! %s\n' "$*" >&2; exit 1; }

command -v muse >/dev/null 2>&1 || die "muse not found on PATH — install Muse Code first."
command -v python3 >/dev/null 2>&1 || die "python3 not found — the margin pane needs it."
command -v tmux >/dev/null 2>&1 || say "? tmux not found — plugin and /margin will work, the side pane will not."

say "· validating $DIR"
muse plugins validate "$DIR" --json >/dev/null || die "plugin validation failed — run: muse plugins validate \"$DIR\" --json"

if muse plugins list --json 2>/dev/null | grep -q '"wonder-margin"'; then
  say "~ already installed — refreshing"
  muse plugins update wonder-margin --json >/dev/null || die "plugin update failed"
else
  say "~ installing plugin (user scope)"
  muse plugins install "$DIR" --scope user --json >/dev/null || die "plugin install failed"
fi

mkdir -p "$BIN_DIR"
ln -sfn "$DIR/muse-margin" "$BIN_DIR/muse-margin"
ln -sfn "$DIR/muse-margin" "$BIN_DIR/muse-margintop"
say "✓ linked $BIN_DIR/muse-margin"

if [ "$WITH_SHIM" = "1" ]; then
  SHIM_DIR="${HOME:-}/.local/share/wonder-margin/bin"
  mkdir -p "$SHIM_DIR"
  ln -sfn "$DIR/shim/muse" "$SHIM_DIR/muse"
  say "✓ linked shim $SHIM_DIR/muse"
  say "  for \`muse --margin\`, put the shim first on PATH in your shell rc:"
  say "    export PATH=\"$SHIM_DIR:\$PATH\""
  say "  plain \`muse\` still forwards to the real binary; only --margin is intercepted."
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "? $BIN_DIR is not on your PATH — add: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

say "✓ done. Open a new terminal and type:  muse-margin"
say "  side is default · muse-margintop (or muse-margin --top) puts me on top"
say "  inside the Muse pane, /margin summons my voice"
