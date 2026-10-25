---
description: Open Cyclops Sideview — a passive side view that leaves tips from the side
argument-hint: "[\"what should the side view watch?\"]"
---

Open Cyclops Sideview — a separate Muse session beside this one that
watches the work and leaves short, relevant tips for the person to pass
along. Use the `muse-sideview` launcher (it must be on PATH; if it is
not, say so and point at the wonder-margin install.sh instead of
improvising — Sideview ships inside the wonder-margin plugin).

Rules:

- If $ARGUMENTS is empty, ask the person what the side view should watch. Do not launch with an invented topic.
- Never put the person's text in a shell command. Write their exact request with your file-writing tool (not the shell) to a uniquely named file in the system temp directory (for example `/tmp/sideview-prompt-<random>.txt`) — never inside the project, where it could be committed. Then pass only that file's path to the launcher with `--prompt-file <path>`; the shell command contains no user text at all. Delete the temp file as soon as the launcher returns, in every mode: the launcher reads the topic at startup and delivers the side prompt itself (by paste in tmux), so nothing needs the file afterwards.
- If we are inside tmux ($TMUX is set), launch `muse-sideview --tmux --prompt-file <path>` so the side view opens in its own pane beside us. Otherwise launch `muse-sideview --once --prompt-file <path>` for one headless tip, and show its output plus the tips-log path it prints.
- Add `--evidence <file>` only for files the person named.
- **Where the comments display:** in the side view's own pane/terminal, and for `--once` also appended to the per-project tips log (`~/.local/state/cyclops-sideview-muse/projects/<cwd-hash>/tips.md`, keyed by the builder's working directory). Nothing is sent to this (builder) session automatically. Say this plainly when you report the launch: the person reads the tip and decides what, if anything, to pass along.
- The side view is passive. It must not edit the builder's files, run the builder's task, or be described as a second driver. If the person wants changes made, that work happens here, in this session, at their direction — not delegated to the side view.
- Report exactly what the launcher printed: side session id if known, receipt path, tips-log path, and how to reach the side view (switch tmux panes; this session stays untouched).
- Be honest about scope: the side view is a new session with no conversation history in its prompt. Project rules and skills still load in it, and its read tools can still reach files on disk. Never claim complete isolation.
