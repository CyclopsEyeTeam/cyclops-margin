# Changelog

## 0.3.2 — 2026-10-24

Second fresh-eyes pass: the contract now holds in the places 0.3.1 missed.

- Shim canonicalises PATH directories; it can no longer exec itself.
- margin-keep only confirms after the write lands, reports failed
  writes/removals, and stores no control characters.
- Sanitisation reaches session-end reason, session id, state text, and
  invisible bidi/zero-width characters.
- Tally is an allowlist (`completed` only); unknown outcomes and nested
  failure/error earn no stroke. The mark leaves a finished deed instead
  of ticking on it. Orphan approval/workflow endings earn no stroke.
- Partial log lines are buffered, the tail read is bounded (2 MB), and
  the model header shows `—` until the host actually configures one.
- Adoption threshold 30s; dedicated runner honours $TMUX_BIN and runs
  under bash; install pre-flights all links; uninstall judges links
  canonically (relative symlinks included).

## 0.3.1 — 2026-10-24

Fresh-eyes review fixes. The pane's honesty contract is unchanged; what
changed is that the code now keeps it under hostile input.

- **Input safety:** arrow keys, pasted text and key bursts can no longer
  trigger copy or quit. Only a lone `c`/`y` copies; bracketed paste is
  enabled and dropped whole.
- **No more leak:** both effect/call ids are retired on every tool
  terminal; the active map no longer grows for the pane's whole life.
- **Sanitisation:** kept lines and logged subjects are stripped of
  control characters (and of `✓`, which untrusted text may not borrow)
  before rendering. An escape in a kept line can no longer draw marks.
- **Parallel calls:** same-file parallel calls count as separate deeds,
  share one display note, and retire it only when the last sibling returns.
- **Tally honesty:** `waited` counts when the wait returns, not when it is
  asked; orphan terminals earn no invented stroke; a subagent branch is
  counted once (at result-ready), not at spawn-call return.
- **tmux manners:** no server-wide (`-g`/`-s`) options anywhere. The
  dedicated session's options die with it; a joined session's mouse and
  history-limit are restored on exit; a failed split now says so.
- **Launchers:** `--margin` is honoured in leading position only, in both
  `muse-margin` and the `muse` shim. Muse's own later `--margin` reaches
  it untouched. Empty-argument expansion is bash 3.2-safe.
- **Installer:** `--help` prints usage and installs nothing; unknown
  arguments are rejected. Links are never created over a stranger's file
  or symlink (targets are canonicalised and compared in full). Uninstall
  removes only links pointing at the checkout. `margin-pane` is linked
  onto PATH and resolves its own symlinks.
- **margin-keep:** newlines are flattened and blank lines refused — one
  kept line is one line.
- Session adoption no longer steals a live session or skips events
  written during the tail read; the button hit-box matches the clipped
  drawing; wide characters count two cells.

## 0.3.0 — 2026-10-24

Second sitting. The tick (`✓`) moved out of the pane into Wonder's voice
only; the kept line became a real file (`margin-keep`); branch, fold,
interrupt and session-end marks; rhythm from the host's own timestamps;
the page-foot tally; the copy-my-last-message button; compact top form.

## 0.1.0 — 2026-10-20

First sitting: the margin itself — a graphite rule, one honest mark at a
time, beside Muse in tmux.
