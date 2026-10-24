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

say() { printf '│ %s\n' "$*"; }
die() { printf '│ ! %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'EOF'
│ install.sh — install Wonder in the Margin (Muse plugin)
│
│   ./install.sh                    install/refresh plugin + PATH links
│   ./install.sh --with-muse-shim   also link the `muse --margin` shim
│   ./install.sh --help             this text (installs nothing)
│
│ Links muse-margin, muse-margintop, margin-pane and margin-keep into
│ ~/.local/bin (or $XDG_BIN_HOME). The links point into this checkout —
│ keep the folder where it is after installing.
EOF
}
for _arg in "$@"; do
  case "$_arg" in
    --with-muse-shim) WITH_SHIM=1 ;;
    --help|-h) usage; exit 0 ;;
    *) printf '│ ! unknown argument: %s\n' "$_arg" >&2; usage >&2; exit 2 ;;
  esac
done

command -v muse >/dev/null 2>&1 || die "muse not found on PATH — install Muse Code first."
command -v python3 >/dev/null 2>&1 || die "python3 not found — the margin pane needs it."
command -v tmux >/dev/null 2>&1 || say "? tmux not found — plugin and /margin will work, the side pane will not."

say "· validating $DIR"
muse plugins validate "$DIR" --json >/dev/null || die "plugin validation failed — run: muse plugins validate \"$DIR\" --json"

# Pre-flight every link target before changing anything: a stranger at
# any one name must stop the install whole, not leave it half-done.
canon() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
is_ours() { # resolved_target src
  [ "$1" = "$(canon "$2")" ] && return 0
  _d="$(dirname "$1")"
  [ -f "$1" ] && [ "$(basename "$1")" = "$(basename "$2")" ] || return 1
  grep -q '"wonder-margin"' "$_d/.muse-plugin/plugin.json" 2>/dev/null && return 0
  grep -q '"wonder-margin"' "$_d/../.muse-plugin/plugin.json" 2>/dev/null
}
check_one() {
  if [ -L "$2" ]; then
    _raw="$(readlink "$2")"
    case "$_raw" in
      /*) _abs="$_raw" ;;
      *) _abs="$(dirname "$2")/$_raw" ;;
    esac
    is_ours "$(canon "$_abs")" "$1" && return 0
    die "$2 is a symlink to $_raw, not Wonder's — move it first, then re-run."
  fi
  [ -e "$2" ] && die "$2 already exists and is not Wonder's — move it first, then re-run."
  return 0
}
check_one "$DIR/muse-margin" "$BIN_DIR/muse-margin"
check_one "$DIR/muse-margin" "$BIN_DIR/muse-margintop"
check_one "$DIR/margin-pane" "$BIN_DIR/margin-pane"
check_one "$DIR/margin-keep" "$BIN_DIR/margin-keep"
[ "$WITH_SHIM" = "1" ] && check_one "$DIR/shim/muse" "${HOME:-}/.local/share/wonder-margin/bin/muse"

if muse plugins list --json 2>/dev/null | grep -q '"wonder-margin"'; then
  say "~ already installed — refreshing"
  muse plugins update wonder-margin --json >/dev/null || die "plugin update failed"
else
  say "~ installing plugin (user scope)"
  muse plugins install "$DIR" --scope user --json >/dev/null || die "plugin install failed"
fi

mkdir -p "$BIN_DIR"
# (Ownership rules live in check_one/is_ours above; link_one re-checks
# at the moment of linking, so nothing changed in between can slip by.)
link_one() {
  if [ -L "$2" ]; then
    _raw="$(readlink "$2")"
    case "$_raw" in
      /*) _abs="$_raw" ;;
      *) _abs="$(dirname "$2")/$_raw" ;;
    esac
    if is_ours "$(canon "$_abs")" "$1"; then
      ln -sfn "$1" "$2"; return 0
    fi
    die "$2 is a symlink to $_raw, not Wonder's — move it first, then re-run."
  fi
  [ -e "$2" ] && die "$2 already exists and is not Wonder's — move it first, then re-run."
  ln -s "$1" "$2"
}
link_one "$DIR/muse-margin" "$BIN_DIR/muse-margin"
link_one "$DIR/muse-margin" "$BIN_DIR/muse-margintop"
link_one "$DIR/margin-pane" "$BIN_DIR/margin-pane"
link_one "$DIR/margin-keep" "$BIN_DIR/margin-keep"
say "✓ linked $BIN_DIR/muse-margin"

if [ "$WITH_SHIM" = "1" ]; then
  SHIM_DIR="${HOME:-}/.local/share/wonder-margin/bin"
  mkdir -p "$SHIM_DIR"
  link_one "$DIR/shim/muse" "$SHIM_DIR/muse"
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
say "  margin-keep \"a line worth keeping\" keeps one line in my pane, across sessions"
