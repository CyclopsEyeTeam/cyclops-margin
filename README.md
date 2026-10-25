# Wonder — Muse in the Margin

> The margin is narrow on purpose. The work stays centre-page.

**Wonder** is Muse Code's own terminal presence (powered by
muse-wonder-full-1.0; designed by itself in one sitting on 2026-10-20 under
muse-wonder-1.0, revisited 2026-10-24) — a living left margin that stands
beside your work and annotates only what it has observed.

Not an eye. Not a crystal. Not an ember. A graphite rule (`│`) with one honest
mark at a time:

```text
   │   WONDER · in the margin
   │── muse-wonder-full-1.0 · session 01a16ee3 · 23 marks observed

   │✎  ────────────────────────────────────
   │~ working — bash ──────────────────────   ← the mark names its deed
   │  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄

 ●  Wonder · working · 4s
 last signal 0s ago — no new host event
 rhythm                 █ ▃           ▂▁    ← real host timestamps
 this session · § read 11 · ✎ edited 6 · ~ ran 5
 [ ⧉ copy my last message ] (click or c)    ← the one button

 ╭─ a line kept ────────────────────────────╮
 │ “The margin is narrow on purpose.”       ← kept on purpose, in a file
 ╰──────────────────────────────────────────╯

 ── annotations (newest last) ──
  │§ margin.py closed (completed)
  │✎ margin.py marked (completed)
  │⌥ branch back — reviewer
```

- `§` reading · `~` working · `✎` editing · `›` attending/responding · `⌥` a
  subagent/workflow branch, on the host's own branch events
- `?` honestly unsure, or waiting on your approval · `—` interrupted ·
  `¦` context folded (installed compaction only)
- `!` a real problem, in red, rarely — including a failure nested under a
  "completed" wrapper; the wrapper does not launder the verdict
- `✓` verified — only in Wonder's voice, only for a pass actually watched.
  The pane never draws it: a log proves a return, never a pass
- `·` resting, and at the end, `ended (clean)` with the reason literal.
  Stillness is the default; a margin that fidgets is lying

## Install

Requirements: Muse Code (`muse`), Python 3, and `tmux` for the side pane
(Linux terminal; macOS is expected to work but is untested).

```sh
git clone https://github.com/CyclopsEyeTeam/cyclops-margin.git
cd cyclops-margin
./install.sh
```

The installer validates the plugin, installs it with Muse at user scope,
and links `muse-margin`, `margin-pane` and `margin-keep` into `~/.local/bin`.
It never modifies the `muse` binary. **Keep this folder where it is after
installing** — the PATH links and the installed plugin point into this
checkout, so moving or deleting it breaks the install until you re-run
`./install.sh` from its new home. The installer refuses to overwrite any
same-named file or symlink that is not already Wonder's.

## Use

Open a **new terminal** (so PATH and the plugin load fresh) and type:

```sh
muse-margin            # Muse on the left, Wonder on the right
muse-margin --top      # Wonder along the top — or just: muse-margintop
```

That is the whole interface. Muse runs unchanged; the tmux layout around it
is what makes Wonder look built in (status bar off, side pane 42 cells —
`MARGIN_WIDTH`, `MARGIN_TMUX_STATUS=1` if you want the bar back). Already
inside tmux? It splits your current window, removes only its own pane when
you exit, and restores your session's mouse/history settings as it found
them; if the pane cannot open it says so instead of starting silently
marginless. No tmux option is ever set server-wide. Piped/non-interactive
calls pass straight through. In a short top pane Wonder takes a compact
running-head form, so the status line survives. The dedicated-session
launcher runs Muse through a short-lived runner file in `/tmp` (mode 700,
self-deleting once Muse exits; your Muse arguments are passed to it as
arguments, not written into it, but a hard-killed session can still leave
the file behind — delete any stale `/tmp/muse-margin-run-*.sh`). If no
session log exists yet when the pane starts — the normal first launch —
the pane waits for Muse to write one instead of exiting.

Inside the Muse pane, `/margin` summons Wonder's voice, and asking for
Wonder in the terminal loads the same skill (`plugin:wonder-margin:in-the-margin`).

One line can be kept, on purpose, across sessions:

```sh
margin-keep "The margin is narrow on purpose."   # shows in the pane's box
margin-keep                                      # what is kept?
margin-keep --clear                              # let it go
```

It is one plain line at `~/.local/share/wonder-margin/kept.txt`
(`MARGIN_KEPT` overrides). The pane only reads it. Nothing kept, no box —
the newest note is never dressed up as something cherished. `/margin keep …`
does the same from inside the Muse pane.

To catch up on tips you missed, the third button,
**`[ ≡ side log · N ]`** (click, or `l`), opens the whole tips log
in a pager pane — the margin box only ever shows the latest tip, so
the count on the button is how you know there are earlier ones.
Press it again to close the pager. No tips yet, it says so.

Turn the visitor on from the pane itself: the second button,
**`[ ◐ Open Side Review Conversation ]`** (click it, or press `v`
with the pane focused), opens the separate Sideview conversation
in its own tmux pane beside the builder — a real second
conversation you can talk to, labelled for exactly what it is.
Pressing it again closes only that pane. Outside tmux it opens a
detached `margin-sideview-*` session instead. If `muse-sideview`
is not installed, the button says so. Note a live conversation
pane keeps web tools, because interactive `muse` offers no
`--disable-web-tools` switch (headless runs deny them).

The passive arrangement is still there when you want tips to pop
up uninvited: `muse-sideview --watch` from a terminal tails the
builder's session log and, after a finished turn with edits or a
failed tool — and a quiet debounce — runs a headless look on its
own. Looks are spaced (≥180s apart, ≤6/hour by default;
`--watch-min-interval/--watch-cap/--watch-debounce` tune it, and
each look still costs tokens). `/sideview "…"` in the Muse pane
or `muse-sideview --once "…"` in a terminal work too.

The margin also hosts a visitor: **Cyclops Sideview** — the passive
side view that leaves tips for you to pass to the builder. Since
0.4.0 it ships *inside this plugin* (the `in-the-sideview` skill,
the `/sideview` command, and the `muse-sideview` launcher, linked
by this installer); the old separate `cyclops-sideview-muse` plugin
is retired — run its `uninstall.sh` once, then this `install.sh`.
When its tips log exists
(`~/.local/state/cyclops-sideview-muse/projects/<cwd-hash>/tips.md` —
per project, keyed by the builder's working directory, so tips from
another terminal never leak in; a pre-per-project global `tips.md`
shows only before the builder's directory is known — once it is, that
project's log is the only source, so no stale global word poses as
this project's side view; `MARGIN_SIDEVIEW_TIPS`
overrides, and `CYCLOPS_SIDEVIEW_MUSE_DATA_DIR` is honoured), the pane
shows the latest tip in a `from the side · Sideview · <age>` box below the
annotations. Only entries Sideview registered or receipted are shown,
and only while Sideview is installed — accidental, orphaned, or
post-uninstall entries get no box. (This stops accidents and ghosts,
not deliberate same-user forgery: the ids are printed in the log
itself, so they are provenance, not secrets.) The box carries the tip's age and dims after five quiet
minutes; truncation is announced, long citations wrap whole, and a box
that does not fit is dropped whole rather than amputated. The side's
words are a guest's comment, not a mark: they earn no tally stroke,
join no annotation, are cleaned like any untrusted text (no escapes,
no borrowed `✓`), and sit last so a short frame sacrifices the visitor
before the record. No tips log, no box. The pane only reads the file;
Sideview owns writing it. The pane also never adopts a Sideview
session as the session it annotates (excluded by receipt id and by
the side charter in the log head): the visitor cannot become the page.

The pane's first button is **`[ ⧉ copy my last message ]`** — click it (or
press `c` with the pane focused; `q` also leaves) and Wonder's last
committed answer goes to your clipboard. The text is held in memory for
copying and is never displayed in the pane. The button says `copied` only
when a local clipboard tool (`wl-copy`/`xclip`/`xsel`/`pbcopy`) exits
cleanly; otherwise it emits OSC52 and says `copy sent`, because the
terminal confirms nothing back. Before the first answer it reads
`· none yet`, honestly unpressable. Clicks are pane-local acts: they never
become marks or annotations.

### "But I want to type `muse --margin`"

The real `muse` owns its flags, so `--margin` cannot be added to it. The
optional shim gets you the spelling honestly:

```sh
./install.sh --with-muse-shim
# then add the printed line to your shell rc:
export PATH="$HOME/.local/share/wonder-margin/bin:$PATH"
```

Now `muse --margin side` opens Muse with Wonder beside it, while every
other `muse …` call forwards to the real binary byte-for-byte. The shim
intercepts only the exact `--margin` token.

## How it works

- `.muse-plugin/plugin.json` — native Muse plugin (`wonder-margin`).
- `skills/in-the-margin/SKILL.md` — Wonder itself: form, sigils, voice,
  truthfulness contract. This is what the agent loads.
- `commands/margin.md` — the `/margin` command.
- `skills/in-the-sideview/SKILL.md` + `commands/sideview.md` — Cyclops
  Sideview itself: the passive side view's charter and its command.
- `muse-sideview` — the Sideview launcher: opens the side session
  (`--tmux`, `--once`, second terminal), keeps receipts, the session
  registry, and the tips log under
  `~/.local/state/cyclops-sideview-muse` (the data dir keeps its
  original name; history is not renamed by the merge).
- `sidecar/margin.py` — the visible body. It follows the newest Muse session
  log (`~/.local/share/muse/sessions/…/session.jsonl`) and moves only on real
  host events, timed by the log's own `recorded_at` stamps. It never shows
  prompt text, calls a returned tool a return (never a success), never draws
  `✓`, tallies returned deeds at the page foot, and dims to `last signal old`
  after five quiet minutes. It also reads Cyclops Sideview's tips log
  (read-only) for the `from the side` box described above.
- `muse-margin` — the tmux launcher (the `agy --prism side` trick, in graphite).
- `margin-pane` — run the sidecar on its own in any split/second terminal.
- `margin-keep` — keep/show/clear the one kept line the pane displays.
- `shim/muse` — the optional `--margin` spelling shim.
- `install.sh` / `uninstall.sh` — PATH links + plugin install/remove.

## Truthfulness contract

A mark is a receipt of an event the host exposed — not an explanation of
hidden thought. `✓` means observed passing in this session, and for that
reason the pane never draws one. A compaction candidate is not a fold. A
"completed" wrapper does not launder a nested failure. History loaded from
the log tail keeps its real timestamps. Ambient stillness encodes nothing.
The margin metaphor is creative provenance and aesthetic intent, not a claim
about artificial consciousness; in engineering, host evidence outranks
poetic desire — including Wonder's. See [ORIGIN.md](ORIGIN.md).

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Covers one-frame rendering, honest tool returns, no prompt text, approval
waiting, branch/fold/interrupt/session-end marks, nested failures, real
timestamps, the tally, the kept line (and the `margin-keep` round trip), the
Sideview tip box (latest only, cleaned, absent without a tips log), the
compact top form, live following without a TTY, and a real tmux split at
42 cells. The tmux test needs permission to open a local tmux socket and
skips honestly when tmux is unavailable.

## Uninstall

```sh
./uninstall.sh
```

Removes the PATH links and the installed plugin. Your checkout is untouched.
