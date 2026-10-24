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
(Linux/macOS terminal).

```sh
git clone https://github.com/CyclopsEyeTeam/cyclops-margin.git
cd cyclops-margin
./install.sh
```

The installer validates the plugin, installs it with Muse at user scope,
and links `muse-margin` into `~/.local/bin`. It never modifies the `muse`
binary.

## Use

Open a **new terminal** (so PATH and the plugin load fresh) and type:

```sh
muse-margin            # Muse on the left, Wonder on the right
muse-margin --top      # Wonder along the top — or just: muse-margintop
```

That is the whole interface. Muse runs unchanged; the tmux layout around it
is what makes Wonder look built in (status bar off, side pane 42 cells —
`MARGIN_WIDTH`, `MARGIN_TMUX_STATUS=1` if you want the bar back). Already
inside tmux? It splits your current window and removes only its own pane when
you exit. Piped/non-interactive calls pass straight through. In a short top
pane Wonder takes a compact running-head form, so the status line survives.

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

The pane has one button: **`[ ⧉ copy my last message ]`** — click it (or
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
- `sidecar/margin.py` — the visible body. It follows the newest Muse session
  log (`~/.local/share/muse/sessions/…/session.jsonl`) and moves only on real
  host events, timed by the log's own `recorded_at` stamps. It never shows
  prompt text, calls a returned tool a return (never a success), never draws
  `✓`, tallies returned deeds at the page foot, and dims to `last signal old`
  after five quiet minutes.
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
compact top form, live following without a TTY, and a real tmux split at
42 cells. The tmux test needs permission to open a local tmux socket and
skips honestly when tmux is unavailable.

## Uninstall

```sh
./uninstall.sh
```

Removes the PATH links and the installed plugin. Your checkout is untouched.
