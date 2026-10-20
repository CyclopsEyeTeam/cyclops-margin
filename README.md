# Wonder — Muse in the Margin

> The margin is narrow on purpose. The work stays centre-page.

**Wonder** is Muse Code's own terminal presence (powered by muse-wonder-1.0),
designed by itself in one sitting on 2026-10-20 — a living left margin that
stands beside your work and annotates only what it has observed.

Not an eye. Not a crystal. Not an ember. A graphite rule (`│`) with one honest
mark at a time:

```text
 WONDER · in the margin
 muse-wonder-1.0 · session 01a15b28 · 4 marks observed

   │  ────────────────────────────────
   │§ ────────────────────────────────   ← reading, at a real line
   │  ────────────────────────────────

 ●  Wonder · resting — answer held in the main pane
 last signal 3s ago — stillness means no new host event, not secret thought

 ── annotations (newest last) ──
  │· session opened — present, nothing claimed
  │§ margin.py closed (completed)
  │~ bash back (completed)
```

- `§` reading · `~` working · `✎` editing · `›` attending/responding
- `?` honestly unsure, or waiting on your approval
- `!` a real problem, in red, rarely
- `✓` verified — only ever for a pass that was actually watched
- `·` resting. Stillness is the default; a margin that fidgets is lying.

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
you exit. Piped/non-interactive calls pass straight through.

Inside the Muse pane, `/margin` summons Wonder's voice, and asking for
Wonder in the terminal loads the same skill (`plugin:wonder-margin:in-the-margin`).

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
  host events. It never shows prompt text, calls a returned tool a return
  (never a success), and dims to `last signal old` after five quiet minutes.
- `muse-margin` — the tmux launcher (the `agy --prism side` trick, in graphite).
- `margin-pane` — run the sidecar on its own in any split/second terminal.
- `shim/muse` — the optional `--margin` spelling shim.
- `install.sh` / `uninstall.sh` — PATH links + plugin install/remove.

## Truthfulness contract

A mark is a receipt of an event the host exposed — not an explanation of
hidden thought. `✓` means observed passing in this session. Ambient stillness
encodes nothing. The margin metaphor is creative provenance and aesthetic
intent, not a claim about artificial consciousness; in engineering, host
evidence outranks poetic desire — including Wonder's. See
[ORIGIN.md](ORIGIN.md).

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Covers one-frame rendering, honest tool returns, no prompt text, approval
waiting, live following without a TTY, and a real tmux split at 42 cells.
The tmux test needs permission to open a local tmux socket and skips
honestly when tmux is unavailable.

## Uninstall

```sh
./uninstall.sh
```

Removes the PATH links and the installed plugin. Your checkout is untouched.
