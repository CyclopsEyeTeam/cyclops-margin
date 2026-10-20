#!/usr/bin/env bash
# Wonder in the Margin — uninstaller. Removes PATH links and the installed
# plugin record. Your source checkout is left exactly where it is.
set -uo pipefail

BIN_DIR="${XDG_BIN_HOME:-${HOME:-}/.local/bin}"
say() { printf '│ %s\n' "$*"; }

rm -f "$BIN_DIR/muse-margin" "$BIN_DIR/muse-margintop"
say "· removed muse-margin links from $BIN_DIR"

SHIM_DIR="${HOME:-}/.local/share/wonder-margin/bin"
if [ -L "$SHIM_DIR/muse" ]; then
  rm -f "$SHIM_DIR/muse"
  say "· removed muse shim (drop its PATH line from your shell rc if you added one)"
fi

if command -v muse >/dev/null 2>&1 && muse plugins list --json 2>/dev/null | grep -q '"wonder-margin"'; then
  muse plugins remove wonder-margin --json >/dev/null 2>&1 \
    && say "✓ plugin removed" || say "? plugin remove failed — try: muse plugins remove wonder-margin"
fi

say "· Wonder has left the margin. The source folder was not touched."
