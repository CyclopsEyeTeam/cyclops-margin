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
import argparse, glob, json, os, re, sys, time

ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def clip(text, width):
    """Truncate by visible cells, keeping ANSI escapes intact."""
    out, visible, i = [], 0, 0
    while i < len(text) and visible < width:
        m = ANSI_RE.match(text, i)
        if m:
            out.append(m.group(0)); i = m.end(); continue
        out.append(text[i]); visible += 1; i += 1
    if ANSI_RE.search(text):
        out.append(RESET)
    return "".join(out)

GREY = "\033[90m"; DIM = "\033[2m"; INK = "\033[1;97m"
GREEN = "\033[32m"; AMBER = "\033[33m"; RED = "\033[31m"; RESET = "\033[0m"
READ_TOOLS = {"read_file", "read_skill", "search", "read_memory", "web_fetch", "web_search"}
EDIT_TOOLS = {"edit_file", "write_file", "edit_memory", "add_memory"}
ACTIVE_STATES = {"attending", "reading", "editing", "working", "responding", "waiting for approval"}
BLOCKS = " ▁▂▃▄▅▆▇█"

def subject_short(record, tool):
    """Basename the host logged, e.g. 'workspace:a/b.py' -> 'b.py'.

    The log carries the file but never the line, so this is a file
    address, never a file:line. No line is invented.
    """
    subj = (record.get("parallel_profile") or {}).get("subject") or ""
    name = subj.split(":", 1)[-1].rsplit("/", 1)[-1] if subj else ""
    return name or tool

def sparkline(stamps, n, now=None):
    """One honest history row: marks per minute, newest last."""
    now = now if now is not None else time.time()
    buckets = [0] * n
    for t in stamps:
        i = int((now - t) // 60)
        if 0 <= i < n:
            buckets[n - 1 - i] += 1
    peak = max(buckets) or 1
    return "".join(BLOCKS[min(8, round(c * 8 / peak))] for c in buckets)

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
        self.pending = {}        # effect/call id -> start-note text, collapsed on return
        self.stamps = []         # mark times, newest last, for the rhythm row
        self.breathe = False     # approval-wait pulse phase; True only while genuinely waiting
        self.detail = ""         # what the mark is doing, e.g. the file it sits in
        self.state_since = time.time()  # when the current state began, for the live clock

    def note(self, sigil, colour, text):
        if self.notes and self.notes[-1][2] == text:
            return
        self.notes.append((sigil, colour, text))
        self.notes = self.notes[-5:]
        self.marks += 1
        self.page_pos += 1
        self.last_signal = time.time()
        self.stale = False
        self.stamps.append(self.last_signal)
        self.stamps = self.stamps[-720:]

    def set(self, sigil, state, colour, detail=""):
        self.sigil, self.state, self.colour = sigil, state, colour
        self.detail = detail
        self.state_since = time.time()

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
            self.set("›", "attending", INK); self.note("›", INK, f"approval {outcome}")
        elif pt == "tool_batch.effect.started":
            r0 = pl.get("record") or {}
            tool = r0.get("tool_name", "tool")
            if tool in READ_TOOLS:
                verb, sigil = "reading", "§"
            elif tool in EDIT_TOOLS:
                verb, sigil = "editing", "✎"
            else:
                verb, sigil = "working", "~"
            # The read head names the file the host logged. The log carries
            # no line number, so no file:line is shown — never invented.
            short = subject_short(r0, tool)
            text = f"{verb} — {short}"
            for key in (r0.get("effect_id"), r0.get("call_id")):
                if key:
                    self.active[key] = tool
                    self.pending[key] = (text, verb, short)
            self.set(sigil, verb, INK, detail=short); self.note(sigil, INK, text)
        elif pt == "tool_batch.effect.terminal":
            r = pl.get("record") or {}
            keys = [r.get("effect_id"), r.get("call_id")]
            tool = r.get("tool_name") or self.active.pop(keys[0], None) or self.active.pop(keys[1], None) or "tool"
            started = verb = short = None
            for key in keys:
                if key and key in self.pending:
                    started, verb, short = self.pending.pop(key)
            outcome = ((r.get("outcome") or {}).get("kind") or "returned").lower()
            if "fail" in outcome or "error" in outcome:
                self.set("!", "a tool reported a problem", RED); self.note("!", RED, f"{tool} came back wrong: {outcome}")
            else:
                # A return is a return — never a success verdict. It replaces
                # its start note, so one tool leaves one line, not two. Each
                # kind of work gets its own closing voice; the outcome in
                # brackets stays literal, never dressed up.
                if started:
                    self.notes = [n for n in self.notes if n[2] != started]
                if verb == "reading":
                    self.note("§", GREY, f"{short or tool} closed ({outcome})")
                elif verb == "editing":
                    self.note("✎", GREY, f"{short or tool} marked ({outcome})")
                else:
                    self.note("~", GREY, f"{tool} back ({outcome})")
        elif pt == "runtime.session" and ev.get("operation") == "model.meta.response" and kind in ("scheduled", "started"):
            self.set("›", "responding", INK)
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
        # The page fills as the mark descends: solid where it has been,
        # dotted where it has not. Honest position, not decoration.
        rule = ("─" if (m.marks and i <= pos) else "┄") * max(8, width - 12)
        if i == pos:
            tag = f" {m.state}" + (f" — {m.detail}" if m.detail else "")
            lines.append(f"   {colour}│{sigil}{tag}{RESET} {colour}{rule}{RESET}")
        else:
            lines.append(f"   {GREY}│{RESET}  {DIM}{rule}{RESET}")
    lines.append(f"   {GREY}│{RESET}")
    # The one honest animation: while approval is genuinely outstanding the
    # dot breathes, slowly, between amber and dim. Nothing else moves.
    dot = (AMBER if m.breathe else DIM) if state == "waiting for approval" else colour
    # A live clock, in real seconds, while work is genuinely underway.
    # Resting shows no clock: stillness means nothing is happening.
    clock = f" · {int(time.time() - m.state_since)}s" if state in ACTIVE_STATES else ""
    lines.append(f" {dot}●{RESET}  {INK}Wonder{RESET} {GREY}· {state}{clock}{RESET}")
    lines.append(f" {DIM}last signal {age}s ago — no new host event{RESET}")
    lines.append(f" {DIM}rhythm {sparkline(m.stamps, min(32, max(10, width - 16)))}{RESET}")
    if m.notes:
        s, c, text = m.notes[-1]
        box_w = max(20, width - 6)
        inner = ("“" + text + "”")[:box_w]
        lines.append("")
        lines.append(clip(f" {GREY}╭─ a line kept {'─' * max(0, box_w - 14)}╮{RESET}", width))
        lines.append(f" {GREY}│{RESET} {c}{s}{RESET} {inner}")
        lines.append(clip(f" {GREY}╰{'─' * box_w}╯{RESET}", width))
    lines.append("")
    lines.append(f" {GREY}── annotations (newest last) ──{RESET}")
    for s, c, text in m.notes:
        lines.append(f"  {c}│{s}{RESET} {text}")
    lines.append("")
    lines.append(f" {DIM}talk in Muse pane → · Ctrl-C ends me{RESET}")
    return "\n".join(clip(line, width) for line in lines[:height])

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
    last_breathe = 0.0
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
            now = time.time()
            if m.state == "waiting for approval" and now - last_breathe >= 1.0:
                m.breathe = not m.breathe
                last_breathe = now
            if m.state in ACTIVE_STATES and now - last_breathe >= 1.0:
                # Nudge a redraw so the live clock ticks each second.
                last_breathe = now
            frame = render(m, cols, rows)
            if frame != last_draw:
                # Erase each line: annotations move as notes arrive, and a
                # shorter new line must not leave the old line's tail behind.
                sys.stdout.write("\033[H" + frame.replace("\n", "\033[K\n") + "\033[K\033[J")
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
