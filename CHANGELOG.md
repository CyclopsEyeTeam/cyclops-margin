# Changelog

## 0.4.8

- No legacy-global fallback once the builder's cwd is known: a
  project with no tips log of its own now shows no side box and a
  `side log · none yet` button, instead of the pre-per-project global
  log's latest entry (another project's stale "nothing from the
  side", age-labelled but still presented as this project's word).
  The global log is read only in the first moments before route
  facts name the cwd.

## 0.4.7

- `MARGIN_SIDEVIEW_TIPS` is honoured again: the env override (like a
  constructor path) is explicit, so per-project re-resolution never
  overwrites it on the first look.
- The `[ ≡ side log · N ]` count now streams the whole log instead of
  counting only the 256 KiB tail — 300 entries report 300.
- Watcher honesty: a failed edit counts as a failure, never an edit;
  tool matching is exact (no `"edit" in tool` substring); started
  records are consumed even when the terminal names its own tool, so
  edited paths no longer leak. `run_interactive` writes no "session
  opened" note when `muse` exits non-zero before any session exists.
  `--watch` refuses a topic, `--evidence` and `--prepare-only` instead
  of silently ignoring them. The compact side line is dropped whole
  when it does not fit (dead `box_end` branch removed).
- Installer heals a moved checkout: the recorded plugin source is
  compared with this directory (structured `plugins list` parsing,
  never a substring grep — same in `uninstall.sh`), and a mismatch
  reinstalls from here instead of updating the old record.
- `margin-keep --help` prints usage and keeps nothing; unknown flags
  and extra words after `--stdin`/`--help` refuse with exit 2 instead
  of becoming the kept line.
- Stale pre-per-project tips paths corrected in `/sideview`, the
  margin skill, and the launcher docstring. Tests no longer use the
  deprecated `load_module()`.

## 0.4.6

- Tips are per-project: Sideview writes
  `projects/<sha256(resolved cwd)[:16]>/tips.md` (with a `project.txt`
  marker naming the directory) instead of one global log, and the
  margin resolves the same path from the builder's cwd — a tip from
  another terminal/project no longer shows in this pane. The legacy
  global `tips.md` still displays until that project has its own log;
  `MARGIN_SIDEVIEW_TIPS` remains an exact-path override. Receipts and
  the session registry stay global (keyed by session, not project).
  A contract test pins the hash scheme on both sides.

## 0.4.5 — 2026-10-25

The watcher's turn-end signal was invented; now it's the host's.
A side look against a real builder log found `run.terminal.*`
appears in no real log — the actual signal is `runtime.session`
with `payload.event.kind == assistant_message_committed` (the same
one the margin rests on), verified against a live log before and
after the fix (a real-log slice now feeds edits and turn-end
correctly). Two companions from the same look: adoption no longer
deadlocks after a fired look (session end is tracked outside the
consumed signal flags), and edited-file subjects now flow from
started records (`parallel_profile.subject`) into the look's
evidence instead of plumbing that carried nothing.

## 0.4.4 — 2026-10-25

The button says what it opens. The Sideview button is now labelled
`[ ◐ Open Side Review Conversation ]` (open: `Side Review: open`)
and opens the separate Sideview conversation again — the 0.4.3
watcher launch was a detour; the passive `--watch` mode remains
available from a terminal for tips that pop up uninvited, but the
button's job is the built-in second conversation, marked well.

## 0.4.3 — 2026-10-25

Sideview goes passive. `muse-sideview --watch` tails the builder's
session log (the same Muse store Wonder reads, Sideview sessions
excluded) and looks on its own: after a finished turn with edits,
or a failed tool, once things have been quiet for a debounce
(20s), spaced at least 180s apart and capped at 6 looks/hour —
each look is a normal headless `--once`, so tips pop into the
margin box and log without anybody prompting the side view. The
margin's Sideview button now launches the watcher instead of a
prompted conversation; `/sideview` and `--tmux` remain for when
you want to talk to it. Watcher triggers are pure, unit-tested
logic; the loop only does I/O.

Also: the README no longer claims the pane "has one button" (it
has three), and the live-pane web-tools asymmetry is documented
where it belongs — interactive `muse` rejects
`--disable-web-tools` outright (verified live), so prompted panes
keep web tools while headless looks deny them.

## 0.4.2 — 2026-10-25

Launch regression fixed (reported live: `muse-margin` outside tmux
printed "margin pane could not open" then "no sessions"). The 0.4.1
stepwise dedicated-session creation set `destroy-unattached` on a
still-detached session, which tmux destroys instantly — before the
split, before attach. Now the session is created at the real
terminal size, the split is attempted and reported, and
`destroy-unattached` is armed only as the client attaches. A
dedicated-path launcher test (previously only the in-tmux split was
covered) pins it.

## 0.4.1 — 2026-10-25

A fresh-eyes pass over the merged plugin, fixed in its order:

- Provenance race closed: live notes register before they append,
  and the pane's entry cache is keyed on the known-id set — a tip
  whose registration lands a render later appears immediately.
- Mouse wheel (64/65) is never a click: scrolling over a button can
  no longer copy, open the log, or launch a side session.
- Prompt privacy: tmux side prompts are pasted through a tmux buffer
  (deleted after use), never embedded in `ps`-visible argv or the
  pane's retained start command; `/sideview`'s temp topic file is
  deletable as soon as the launcher returns. Headless receipts now
  delete `prompt.txt` when the run ends (hash and topic preview
  stay). The plain-terminal interactive path still passes its prompt
  as an argument — documented, and the reason `/sideview` prefers
  tmux/`--once`.
- `/margin keep` no longer puts words in a shell command: the line
  goes through a temp file into the new `margin-keep --stdin`.
- Smaller: rotation+append under one flock; installed-check cache
  shared by box and count; adoption checks throttled to 10s with a
  bounded charter cache; first-intent charter detection requires the
  charter as the opening and is depth-guarded; SIGTERM/SIGHUP
  restore the pane terminal (and the launcher traps HUP); the
  dedicated-session split failure now warns instead of going
  quietly marginless; `--timeout=-1` and `margin-keep --clear
  <words>` refuse cleanly; the uninstaller no longer claims success
  when `muse` is absent.

## 0.4.0 — 2026-10-25

One plugin. Cyclops Sideview moves into wonder-margin: the
`in-the-sideview` skill, the `/sideview` command, and the
`muse-sideview` launcher now ship, install, and uninstall with
Wonder. The separate `cyclops-sideview-muse` plugin is retired.

- Migration: run the old plugin's `uninstall.sh` first (it removes
  its PATH link and plugin record; tips and receipts stay), then
  this `install.sh`. The margin installer now links `muse-sideview`
  alongside its existing links, with the same pre-flight ownership
  checks.
- Nothing about the bridge changes at runtime: same tips log,
  registry, and receipts under `~/.local/state/cyclops-sideview-muse`
  (the data dir keeps its name — history is not renamed), same pane
  display and provenance gates. The installed-check now reads the
  `wonder-margin` record, since that is the plugin that ships it.
- Sideview's tests move in too; the cross-plugin contract tests are
  now intra-plugin and can no longer skip a missing sibling.

## 0.3.9 — 2026-10-25

Read the whole visit, not just the last word. The pane now has a
third button, `[ ≡ side log · N ]` (click it, or press `l`).

- The label carries the verified entry count, so five tips in an
  hour never silently collapse to the newest: the box still shows
  only the latest, but the count says there are four more.
- Pressing it opens the full tips log in a pager (`less`/`more`)
  pane beside the builder; pressing again closes only that pane.
  No tips yet: the button says `none yet` and opens nothing.

## 0.3.8 — 2026-10-25

The visitor gets a doorbell. The pane now has a second button,
`[ ◐ side view: off ]` (click it, or press `v` with the pane focused).

- On: launches `muse-sideview` in its own tmux pane beside the
  builder (a detached `margin-sideview-*` session outside tmux)
  watching the builder's cwd from the host's route facts.
- Off: kills only the pane/session this margin opened. A side pane
  that closed itself is detected on the next press and reopened
  instead of the button lying about being on.
- No `muse-sideview` on PATH: the button says so instead of failing
  silently. The toggle is a pane-local act — no mark, no tally —
  and the visitor's target survives session adoption.

## 0.3.7 — 2026-10-25

The bridge, unstuck. A fresh-eyes pass over 0.3.6 found the display
could silently stick to the wrong file and the tmux path had no real
id; provenance wording is now honest about its limits.

- The pane re-resolves the tips path on every look, so an
  `active-data-dir.txt` change reaches a running pane; Sideview
  clears that pointer when a run returns to the default dir.
- Tmux side sessions get a real registered session id (polled from
  the session store, FreshEye-style); interactive receipts already
  had one. The id exclusion no longer leans on the charter heuristic
  in the flagship configuration.
- Provenance is stated honestly: registered-id display stops
  accidental, orphaned, and post-uninstall entries. It does not stop
  deliberate same-user forgery — the ids are not secrets, and the
  docs no longer imply otherwise.
- The installed check honours XDG_DATA_HOME and is cached (10s).

## 0.3.6 — 2026-10-25

The bridge gets provenance. A fresh-eyes pass found the coupling was
an unversioned shared file with heuristic guards that failed both
ways; the seams are now pinned by a cross-plugin integration test
(the real Sideview launcher's output through the real Margin parser).

- Display provenance: the box shows only entries whose session id
  Sideview registered (`side-sessions.jsonl`) or receipted, and only
  while `cyclops-sideview-muse` is installed and enabled. Forged or
  orphaned entries — and ghosts after an uninstall — get no box.
- Adoption guard, precise both ways: registered ids first; the
  fallback inspects only the session's own `user_intent` record for
  the exact charter opening. A builder that merely read Sideview's
  files is no longer mistaken for the side view, and a side session
  is caught wherever its prompt record lands. Id lookups are
  TTL-cached (10s) instead of re-parsing every receipt every 2s.
- A custom Sideview `--data-dir` registers a pointer in the default
  dir; the pane follows it. One shared path implementation now
  serves the tips log, receipts, and registry.
- An entry larger than the parsed tail announces itself
  (`larger than the margin reads`) instead of vanishing, and the box
  title carries its attribution: `from the side · Sideview · <age>`.

## 0.3.5 — 2026-10-25

The visitor's box, held to the margin's own contract (a fresh-eyes
pass over 0.3.4 found the display layer making claims it could not
back; both suites were green throughout):

- The box now carries its tip's age (`from the side · 2h old`) and
  dims past five quiet minutes, like every other stale signal in the
  pane. An undated entry says `undated`.
- Section-safe parsing: only a strict `## <iso> · side session <id>`
  header opens an entry, entry bodies are `> `-prefixed by the writer,
  and only the log's last 256 KiB is parsed. A `## …` line inside the
  side's own text is body, never a boundary.
- Truncation is announced (`… +n more lines`), long citations are
  hard-wrapped whole instead of clipped mid-path, ANSI sequences are
  stripped whole (no `[31m` debris), and link citations survive as
  `label:line`. A box that does not fit the frame is dropped whole,
  never amputated.
- The pane never adopts a Sideview session as its subject: sessions
  are excluded by Sideview's own receipt ids and by the side charter
  in the log head. The visitor cannot become the page.

## 0.3.4 — 2026-10-25

The margin hosts a visitor. Cyclops Sideview (`cyclops-sideview-muse`),
the passive side view that leaves tips for the person to pass to the
builder, can now display in the pane too.

- New `from the side · Cyclops Sideview` box below the annotations,
  showing the latest tip from Sideview's tips log
  (`~/.local/state/cyclops-sideview-muse/tips.md`;
  `MARGIN_SIDEVIEW_TIPS` overrides, `CYCLOPS_SIDEVIEW_MUSE_DATA_DIR`
  honoured). The pane only reads the file; Sideview owns writing it.
- The side's words are a guest's comment, never a mark: no tally
  stroke, no annotation, cleaned like any untrusted text (control and
  invisible characters stripped, markdown links collapsed to their
  label, the earned `✓` unborrowable). No tips log, no box.
- The box sits last in the frame, so a short pane sacrifices the
  visitor before it sacrifices the record. In the compact top form it
  is one `◐ side ·` line.

## 0.3.3 — 2026-10-25

Third fresh-eyes pass: two dead-or-dying paths found against the real
host, and the shells hardened where the second pass stopped early.

- The `responding` state could never fire: it waited for
  `scheduled`/`started` events carrying `model.meta.response`, a shape
  that occurs zero times in real session logs. The host declares a
  model call as `side_effect_intent` with that operation; the pane
  listens for that now.
- A pane launched beside a just-starting `muse` (the normal
  `muse-margin` launch on a fresh install) exited instantly when no
  session log existed yet. The live pane waits for the first log;
  `--once` still reports and exits. A truncated log no longer strands
  the follow offset past EOF, and `newest_session` survives a log
  vanishing between glob and stat.
- Parallel workflow children sharing one label were counted once;
  labels are counted now, so each branch back earns its stroke.
  US-spelled `canceled` is an interrupt, a future `recorded_at` is
  distrusted instead of showing a negative clock, malformed log
  records are inert instead of raising, and a pane narrower than
  30 cells no longer wraps (the render floor is 10, clipped).
- margin-keep strips carriage returns, bidi/zero-width characters
  and the earned tick on store and show, and writes by temp file +
  rename: a symlink at the kept path is replaced, never followed
  into truncating its target.
- `muse-margin` validates `MARGIN_WIDTH`/`MARGIN_HEIGHT` and checks
  both binaries are executable before any tmux work. The `muse`
  shim judges PATH candidates by resolved file, so alias directories
  symlinking back to the shim cannot make it bounce between them.
  The installer judges another checkout by a manifest that actually
  names the plugin, not by a passing mention of the string.

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
