#!/usr/bin/env python3
"""Wonder in the Margin — a sidecar pane for Muse Code.

Run me in a split or second terminal, beside `muse`:

    python3 margin.py            # follow the newest live session
    python3 margin.py --once     # draw one frame and exit (testing)
    python3 margin.py --session /path/to/session.jsonl

Truthfulness: I only move on events the host actually wrote to its session
log (~/.local/share/muse/sessions/YYYY/MM/DD/<id>/session.jsonl). I never
show prompt text, never call a returned tool a success, and go honestly
stale ("last signal old") when the log goes quiet. Ctrl-C ends me: `·`
"""
import argparse, glob, json, os, sys, time

GREY = "\033[90m"; DIM = "\033[2m"; INK = "\033[1;97m"
GREEN = "\033[32m"; AMBER = "\033[33m"; RED = "\033[31m"; RESET = "\033[0m"
READ_TOOLS = {"read_file", "read_skill", "search", "read_memory", "web_fetch", "web_search"}
EDIT_TOOLS = {"edit_file", "write_file", "edit_memory", "add_memory"}

def newest_session():
    base = os.path.expanduser("~/.local/share/muse/sessions")
    files = glob.glob(os.path.join(base, "*", "*", "*", "*", "session.jsonl"))
    return max(files, key=os.path.getmtime) if files else None

class Margin:
    def __init__(self):
        self.sigil, self.state, self.colour = "·", "resting", GREY
        self.notes = []          # (sigil, colour, text), newest last
        self.marks = 0           # events observed this session
        self.page_pos = 0        # where my mark sits on the page
        self.last_signal = time.time()
        self.session = "—"
        self.model = "muse-wonder-1.0"
        self.stale = False
        self.active = {}         # effect/call id -> tool name, for honest returns

    def note(self, sigil, colour, text):
        self.notes.append((sigil, colour, text))
        self.notes = self.notes[-8:]
        self.marks += 1
        self.page_pos += 1
        self.last_signal = time.time()
        self.stale = False

    def set(self, sigil, state, colour):
        self.sigil, self.state, self.colour = sigil, state, colour

    def feed(self, rec):
        pt = rec.get("payload_type") or ""
        pl = rec.get("payload") or {}
        ev = pl.get("event") or {}
        kind = ev.get("kind") or pl.get("kind") or ""
        if pt == "session.started":
            sid = (rec.get("stream") or {}).get("id", "")
            self.session = sid[:8] if sid else self.session
            self.set("·", "resting", GREY); self.note("·", GREY, "session opened — present, nothing claimed")
        elif pt == "run.model.configured":
            label = (pl.get("record") or {}).get("display_label")
            if label: self.model = label
        elif pt == "runtime.user_intent.accepted":
            self.set("›", "attending", INK); self.note("›", INK, "prompt received (text never shown here)")
        elif pt == "approval_wait.effect.started":
            tool = (pl.get("record") or {}).get("tool_name", "a tool")
            self.set("?", "waiting for approval", AMBER); self.note("?", AMBER, f"approval asked — {tool} held")
        elif pt == "approval_wait.effect.terminal":
            outcome = ((pl.get("record") or {}).get("outcome") or {}).get("kind", "settled")
            self.note("›", INK, f"approval {outcome}")
        elif pt == "tool_batch.effect.started":
            r0 = pl.get("record") or {}
            tool = r0.get("tool_name", "tool")
            for key in (r0.get("effect_id"), r0.get("call_id")):
                if key: self.active[key] = tool
            if tool in READ_TOOLS:
                self.set("§", "reading", INK); self.note("§", INK, f"reading — {tool}")
            elif tool in EDIT_TOOLS:
                self.set("✎", "editing", INK); self.note("✎", INK, f"editing — {tool}")
            else:
                self.set("~", "working", INK); self.note("~", INK, f"working — {tool}")
        elif pt == "tool_batch.effect.terminal":
            r = pl.get("record") or {}
            tool = r.get("tool_name") or self.active.pop(r.get("effect_id"), None) or self.active.pop(r.get("call_id"), None) or "tool"
            outcome = ((r.get("outcome") or {}).get("kind") or "returned").lower()
            if "fail" in outcome or "error" in outcome:
                self.set("!", "a tool reported a problem", RED); self.note("!", RED, f"{tool} returned: {outcome}")
            else:
                # A return is a return — never a success verdict.
                self.note("~", GREY, f"{tool} returned ({outcome})")
        elif pt == "runtime.session" and ev.get("operation") == "model.meta.response" and kind in ("scheduled", "started"):
            self.set("›", "responding", INK); self.note("›", GREY, "answering…")
        elif kind == "assistant_message_committed":
            self.set("·", "resting — answer held in the main pane", GREY)
            self.note("·", GREY, "answer committed; back to stillness")

def render(m, width, height):
    width = max(30, width)
    page_rows = max(6, min(18, height - 22))
    age = int(time.time() - m.last_signal)
    stale = age > 300
    sigil, colour, state = (m.sigil, m.colour, m.state)
    if stale and m.marks:
        state, colour = state + " · last signal old", GREY
    lines = []
    lines.append(f"{INK} WONDER{RESET} {GREY}· in the margin{RESET}")
    lines.append(f" {DIM}{m.model} · session {m.session} · {m.marks} marks observed{RESET}")
    lines.append("")
    pos = m.page_pos % page_rows if page_rows else 0
    for i in range(page_rows):
        rule = "─" * max(8, width - 12)
        if i == pos:
            lines.append(f"   {colour}│{sigil}{RESET} {colour}{rule}{RESET}")
        else:
            lines.append(f"   {GREY}│{RESET}  {DIM}{rule}{RESET}")
    lines.append(f"   {GREY}│{RESET}")
    lines.append(f" {colour}●{RESET}  {INK}Wonder{RESET} {GREY}· {state}{RESET}")
    lines.append(f" {DIM}last signal {age}s ago — stillness means no new host event, not secret thought{RESET}")
    if m.notes:
        s, c, text = m.notes[-1]
        box_w = max(20, width - 6)
        inner = ("“" + text + "”")[:box_w]
        lines.append("")
        lines.append(f" {GREY}╭─ a line kept {'─' * max(0, box_w - 14)}╮{RESET}"[:width + 10])
        lines.append(f" {GREY}│{RESET} {c}{s}{RESET} {inner}")
        lines.append(f" {GREY}╰{'─' * box_w}╯{RESET}"[:width + 10])
    lines.append("")
    lines.append(f" {GREY}── annotations (newest last) ──{RESET}")
    for s, c, text in m.notes:
        lines.append(f"  {c}│{s}{RESET} {text}"[:width])
    lines.append("")
    lines.append(f" {DIM}talk to me in the Muse pane →  ·  Ctrl-C ends me{RESET}")
    return "\n".join(lines[:height])

def term_size():
    try:
        s = os.get_terminal_size()
        return s.columns, s.lines
    except OSError:
        return 48, 44

def load_tail(m, path):
    m.session = os.path.basename(os.path.dirname(path))[:8] or m.session
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            tail = f.readlines()[-3000:]
        for line in tail:
            try: m.feed(json.loads(line))
            except Exception: pass
        m.page_pos = max(0, m.marks - 1)
    except OSError:
        pass

def follow(path, once=False, pinned=False):
    m = Margin()
    # Populate from the tail so a pane opened mid-session is not empty.
    load_tail(m, path)
    if once:
        cols, rows = term_size()
        sys.stdout.write(render(m, cols, rows) + "\n")
        return
    sys.stdout.write("\033[?25l\033[2J")
    offset = os.path.getsize(path)
    last_draw = ""
    last_check = 0.0
    try:
        while True:
            # Unless pinned to one log, adopt a newer session when one starts
            # (the pane is usually launched at the same moment as `muse`).
            if not pinned and time.time() - last_check > 2:
                last_check = time.time()
                newer = newest_session()
                if newer and newer != path:
                    path = newer
                    m = Margin()
                    load_tail(m, path)
                    try: offset = os.path.getsize(path)
                    except OSError: offset = 0
            try:
                cols, rows = term_size()
                with open(path, encoding="utf-8", errors="ignore") as f:
                    f.seek(offset)
                    chunk = f.read()
                    offset = f.tell()
                for line in chunk.splitlines():
                    try: m.feed(json.loads(line))
                    except Exception: pass
            except OSError:
                chunk = ""
            frame = render(m, cols, rows)
            if frame != last_draw:
                sys.stdout.write("\033[H" + frame + "\033[J")
                sys.stdout.flush()
                last_draw = frame
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(f"\033[?25h\n{GREY}· Wonder has left the margin.{RESET}\n")

def main():
    ap = argparse.ArgumentParser(description="Wonder in the Margin — Muse sidecar pane")
    ap.add_argument("--session", help="session.jsonl to watch (default: newest live session)")
    ap.add_argument("--once", action="store_true", help="draw one frame and exit")
    args = ap.parse_args()
    path = args.session or newest_session()
    if not path or not os.path.exists(path):
        print("· No Muse session log found yet — start `muse` first, then run me.")
        return 1
    follow(path, once=args.once, pinned=bool(args.session))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
