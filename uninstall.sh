#!/usr/bin/env bash
# Wonder in the Margin — uninstaller. Removes PATH links and the installed
# plugin record. Your source checkout is left exactly where it is.
set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-${HOME:-}/.local/bin}"
say() { printf '│ %s\n' "$*"; }
usage() {
  cat <<'EOF'
│ uninstall.sh — remove Wonder in the Margin's PATH links and plugin
│
│   ./uninstall.sh          remove links that point at this checkout,
│                           plus the installed plugin record
│   ./uninstall.sh --help   this text (removes nothing)
│
│ Receipts of ownership are checked link by link: a same-named file that
│ is not Wonder's is left exactly where it is. This checkout stays.
EOF
}
for _arg in "$@"; do
  case "$_arg" in
    --help|-h) usage; exit 0 ;;
    *) printf '│ ! unknown argument: %s\n' "$_arg" >&2; usage >&2; exit 2 ;;
  esac
done

# Remove only links that point at this checkout, judged canonically —
# a relative symlink into the checkout is ours just as an absolute one
# is (install.sh accepts both). A same-named file that is not Wonder's
# is the user's, and stays exactly where it is.
canon() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
  else
    printf '%s\n' "$1"
  fi
}
remove_ours() {
  if [ -L "$1" ]; then
    _raw="$(readlink "$1")"
    case "$_raw" in
      /*) _abs="$_raw" ;;
      *) _abs="$(dirname "$1")/$_raw" ;;
    esac
    if [ "$(canon "$_abs")" = "$(canon "$2")" ]; then
      rm -f "$1"
      return 0
    fi
  fi
  if [ -e "$1" ] || [ -L "$1" ]; then
    say "· kept $1 — it does not point at this plugin"
  fi
}
remove_ours "$BIN_DIR/muse-margin" "$DIR/muse-margin"
remove_ours "$BIN_DIR/muse-margintop" "$DIR/muse-margin"
remove_ours "$BIN_DIR/margin-pane" "$DIR/margin-pane"
remove_ours "$BIN_DIR/margin-keep" "$DIR/margin-keep"
remove_ours "$BIN_DIR/muse-sideview" "$DIR/muse-sideview"
say "· removed muse-margin links from $BIN_DIR (any that were Wonder's)"
say "· your kept line, if any, stays at ~/.local/share/wonder-margin/kept.txt — it is yours, not mine to delete"
say "· Sideview tips/receipts stay at ~/.local/state/cyclops-sideview-muse — yours, not mine to delete"

SHIM_DIR="${HOME:-}/.local/share/wonder-margin/bin"
if [ -L "$SHIM_DIR/muse" ]; then
  _had_shim=1
  remove_ours "$SHIM_DIR/muse" "$DIR/shim/muse"
  if [ -n "$_had_shim" ] && [ ! -L "$SHIM_DIR/muse" ]; then
    say "· removed muse shim (drop its PATH line from your shell rc if you added one)"
  fi
fi

if ! command -v muse >/dev/null 2>&1; then
  say "? muse not found — the plugin record was NOT removed; later: muse plugins remove wonder-margin"
plugin_installed() { # structured check, never a substring grep
  muse plugins list --json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
plugins = data.get("plugins", []) if isinstance(data, dict) else data
for entry in plugins:
    plugin = entry.get("plugin", entry) if isinstance(entry, dict) else {}
    if plugin.get("id") == "wonder-margin" or plugin.get("name") == "wonder-margin":
        sys.exit(0)
sys.exit(1)'
}
elif plugin_installed; then
  muse plugins remove wonder-margin --json >/dev/null 2>&1 \
    && say "✓ plugin removed" || say "? plugin remove failed — try: muse plugins remove wonder-margin"
else
  say "· plugin was not installed"
fi

say "· Wonder has left the margin. The source folder was not touched."
