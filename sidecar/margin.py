#!/usr/bin/env python3
"""Wonder in the Margin — a sidecar pane for Muse Code.

Run me in a split or second terminal, beside `muse`:

    python3 margin.py            # follow the newest live session
    python3 margin.py --once     # draw one frame and exit (testing)
    python3 margin.py --session /path/to/session.jsonl

Truthfulness: I only move on events the host actually wrote to its session
log (~/.local/share/muse/sessions/YYYY/MM/DD/<id>/session.jsonl). I never
show prompt text, never call a returned tool a success, and go honestly
stale ("last signal old") when the log goes quiet. I never draw `✓`: the log
can prove a tool returned, never that tests passed — the tick lives only in
Wonder's voice, after a pass was actually watched. Ctrl-C ends me: `·`

Second sitting (2026-10-24): real log timestamps (`recorded_at`), branch
marks for subagents/workflows, the compaction fold, interrupts, session
end, a per-session tally of deeds, a kept line that is actually kept (in a
file, across sessions — see `margin-keep`), a compact running-head
form for short top panes, and a `from the side` box showing Cyclops
Sideview's latest tip (its tips log, read-only here; absent, no box).
Plus one button: `[ ⧉ copy my last message ]`
(click it, or press `c`; `q` also leaves). The last committed answer is
held for copying and never rendered; the button says `copied` only when a
local clipboard tool exited cleanly, else `copy sent` for OSC52.
"""
import argparse, base64, glob, json, os, re, select, shutil, subprocess, sys, time, unicodedata

try:
    import termios, tty
except ImportError:  # non-POSIX: the pane still renders, just no clicks
    termios = tty = None

ANSI_RE = re.compile(r"\033\[[0-9;]*m")
MOUSE_RE = re.compile(r"\033\[<(\d+);(\d+);(\d+)([Mm])")
CSI_RE = re.compile(r"\033\[[0-9;?]*[A-Za-z~]")
ESC_RE = re.compile(r"\033.")
PASTE_RE = re.compile(r"\033\[200~[\s\S]*?(?:\033\[201~|$)")
CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
INVIS_RE = re.compile("[" + "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0x00AD, 0xFEFF)) + "]")
ZWJ = chr(0x200D); VS16 = chr(0xFE0F)

def _as_dict(value):
    return value if isinstance(value, dict) else {}


def clean(text):
    """Strip control characters from host-supplied text before rendering.

    A kept line or a logged subject is data, never terminal control: an
    escape in it would let the log draw marks the pane has no right to
    draw. Invisible format characters (bidi overrides, zero-width marks)
    go too: text may not silently reorder the pane. The `✓` glyph is
    also removed — it is Wonder's earned mark, earned only in voice,
    and untrusted text may not borrow it.
    """
    return INVIS_RE.sub("", CTRL_RE.sub("", str(text))).replace("✓", "")

def char_widths(s):
    """Per-character cell widths: wide = 2, combining/ZWJ/VS = 0, and a
    character joined by a ZWJ adds nothing (an emoji family is one glyph)."""
    widths = []
    for i, ch in enumerate(s):
        if unicodedata.combining(ch) or ch in (ZWJ, VS16) or (i and s[i - 1] == ZWJ):
            widths.append(0)
        elif unicodedata.east_asian_width(ch) in ("W", "F"):
            widths.append(2)
        else:
            widths.append(1)
    return widths

def display_width(text):
    """Visible cells of a string, ignoring ANSI escapes."""
    return sum(char_widths(ANSI_RE.sub("", text)))

def clip(text, width):
    """Truncate by visible cells, keeping ANSI escapes intact."""
    out, visible, i = [], 0, 0
    wlist = char_widths(ANSI_RE.sub("", text))
    ci = 0
    while i < len(text) and visible < width:
        m = ANSI_RE.match(text, i)
        if m:
            out.append(m.group(0)); i = m.end(); continue
        w = wlist[ci]; ci += 1
        if visible + w > width:
            break
        out.append(text[i]); visible += w; i += 1
    if ANSI_RE.search(text):
        out.append(RESET)
    return "".join(out)

GREY = "\033[90m"; DIM = "\033[2m"; INK = "\033[1;97m"
AMBER = "\033[33m"; RED = "\033[31m"; RESET = "\033[0m"
REV = "\033[7m"  # reverse video: the copy button, pressed
READ_TOOLS = {"read_file", "read_skill", "search", "read_memory", "web_fetch", "web_search",
              "subagent_status", "subagent_read_result", "work_list", "work_status",
              "list_peer_sessions", "cron_list", "get_goal"}
EDIT_TOOLS = {"edit_file", "write_file", "edit_memory", "add_memory", "write_todos",
              "cron_create", "cron_delete", "create_goal", "update_goal"}
BRANCH_TOOLS = {"subagent_spawn", "workflow"}   # work that steps out from the rule
WATCH_TOOLS = {"monitor", "subagent_wait"}      # waiting on something real, elsewhere
ACTIVE_STATES = {"attending", "reading", "editing", "working", "responding",
                 "waiting for approval", "branching", "watching"}
BLOCKS = " ▁▂▃▄▅▆▇█"
KEPT_DEFAULT = "~/.local/share/wonder-margin/kept.txt"

def sideview_data_dir():
    """Sideview's default data dir (single source for both path needs).

    Kept byte-compatible with Sideview's own default_data_dir(); the
    cross-plugin integration test pins the env names and layout so the
    two implementations cannot silently drift apart.
    """
    override = os.environ.get("CYCLOPS_SIDEVIEW_MUSE_DATA_DIR")
    if override:
        return os.path.expanduser(override)
    xdg = os.environ.get("XDG_STATE_HOME")
    base = os.path.expanduser(xdg) if xdg else os.path.expanduser("~/.local/state")
    return os.path.join(base, "cyclops-sideview-muse")


def effective_sideview_data_dir():
    """The data dir Sideview most recently registered a session in.

    A custom --data-dir run leaves a pointer in the default dir; the
    bridge follows it instead of silently showing nothing.
    """
    default = sideview_data_dir()
    try:
        with open(os.path.join(default, "active-data-dir.txt"),
                  encoding="utf-8", errors="ignore") as f:
            pointed = f.readline().strip()
        if pointed and os.path.isdir(pointed):
            return pointed
    except OSError:
        pass
    return default


def sideview_tips_default():
    """Where Cyclops Sideview leaves its tips log.

    The pane only ever reads this file; Sideview owns writing it. No
    file, no box — the margin never invents a side comment.
    """
    return os.path.join(effective_sideview_data_dir(), "tips.md")


def project_tips_path(data_dir, cwd):
    """Per-project tips log: sha256(resolved cwd)[:16] under projects/.

    Byte-compatible with Sideview's own project_tips_path — the
    contract test pins the scheme so writer and reader cannot drift.
    """
    import hashlib
    key = hashlib.sha256(os.path.realpath(os.path.expanduser(str(cwd))).encode("utf-8")).hexdigest()[:16]
    return os.path.join(str(data_dir), "projects", key, "tips.md")


SIDEVIEW_HEADER_RE = re.compile(r"^## (\S+) · side session (\S+)\s*$")
SIDEVIEW_TAIL_BYTES = 256 * 1024


def _sideview_link(m):
    label, target = m.group(1), m.group(2)
    if target.startswith(("http://", "https://")):
        return label
    line_no = re.search(r":(\d+)$", target)
    if line_no and "/" in target:
        return f"{label}:{line_no.group(1)}"
    if "/" in target:
        base = target.rsplit("/", 1)[-1]
        return f"{label} ({base})" if base and base != label else label
    return f"{label} ({target})"


def _sideview_display_line(line):
    line = CSI_RE.sub("", line)
    line = ESC_RE.sub("", line)
    line = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", _sideview_link, line)
    return clean(line.replace("`", "")).rstrip()


def latest_sideview_entry(text):
    """The newest Sideview entry: {"created": epoch|None, "text": str}.

    Sections begin only at a strict `## <iso> · side session <id>`
    header, and body lines written by the launcher are `> `-prefixed —
    a `## …` line inside the model's own text is body, never a new
    section. Legacy unprefixed bodies still parse. Markdown links keep
    their citation (label:line), backticks go, ANSI sequences are
    stripped whole, and every line passes `clean` — the side's text is
    data here, never terminal control, and may not borrow the `✓`.
    """
    return sideview_entries(text)[-1] if sideview_entries(text) else {
        "created": None, "text": "", "session": None}


def sideview_entries(text):
    """Every entry in a tips log, oldest first (see latest_sideview_entry)."""
    sections, current = [], None
    for line in str(text).splitlines():
        m = SIDEVIEW_HEADER_RE.match(line)
        if m:
            if current is not None:
                sections.append(current)
            current = ((m.group(1), m.group(2)), [])
        elif current is not None:
            current[1].append(line)
    if current is not None:
        sections.append(current)
    entries = []
    for (created_raw, session_id), body in sections:
        created = None
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(
                created_raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            created = None
        body = list(body)
        while body and not body[0].strip():
            body.pop(0)
        if body and (body[0].startswith("Watched:") or body[0].startswith("> Watched:")):
            body.pop(0)
            while body and not body[0].strip():
                body.pop(0)
        out = []
        for line in body:
            if line.startswith("> "):
                line = line[2:]
            elif line == ">":
                line = ""
            out.append(_sideview_display_line(line))
        entries.append({"created": created,
                        "text": "\n".join(out).strip(),
                        "session": session_id})
    return entries


def latest_sideview_tip(text):
    """The newest tip's text (see latest_sideview_entry)."""
    return latest_sideview_entry(text)["text"]


def _split_word(word, width):
    chunks, cur = [], ""
    for ch, w in zip(word, char_widths(word)):
        if cur and display_width(cur) + w > width:
            chunks.append(cur)
            cur = ""
        cur += ch
    if cur:
        chunks.append(cur)
    return chunks or [""]


def wrap_text(text, width):
    """Word-wrap plain text to `width` cells.

    A word longer than the line (a path/to/file.py:1234 citation) is
    hard-split across lines rather than clipped mid-token: the whole
    token survives, so its line number is never silently lost.
    """
    width = max(1, width)
    lines = []
    for para in str(text).splitlines():
        words, cur = para.split(), ""
        if not words:
            continue
        for word in words:
            if display_width(word) > width:
                if cur:
                    lines.append(cur)
                    cur = ""
                chunks = _split_word(word, width)
                lines.extend(chunks[:-1])
                cur = chunks[-1]
                continue
            trial = f"{cur} {word}".strip()
            if cur and display_width(trial) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
    return lines

def subject_short(record, tool):
    """Basename the host logged, e.g. 'workspace:a/b.py' -> 'b.py'.

    The log carries the file but never the line, so this is a file
    address, never a file:line. No line is invented.
    """
    subj = _as_dict(record.get("parallel_profile")).get("subject") or ""
    if not isinstance(subj, str):
        subj = str(subj)
    name = subj.split(":", 1)[-1].rsplit("/", 1)[-1] if subj else ""
    if not name and tool.startswith("mcp__"):
        name = tool.rsplit("__", 1)[-1]  # mcp__server__room_read -> room_read
    return clean(name or tool)


def event_time(record):
    """The host's own clock: `recorded_at` is microseconds since the epoch.

    History loaded from the tail keeps its real ages — the rhythm row and
    the stale check must never pretend old marks happened just now.
    """
    raw = record.get("recorded_at")
    try:
        at = float(raw) / 1_000_000.0
    except (TypeError, ValueError):
        return None
    # A stamp far in the future is a corrupt/skewed clock, not evidence:
    # trusting it would show negative ages and freeze the stale check.
    if at <= 1_000_000_000 or at > time.time() + 300:
        return None
    return at

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

_KNOWN_IDS_CACHE = {"at": 0.0, "ids": set(), "dirs": None}


def known_sideview_session_ids():
    """Ids Sideview itself registered or receipted (10s TTL cache).

    Sources: the side-sessions registry (default and effective data
    dirs) and receipt side_session_ids in the effective data dir.
    The follow loop asks every 2s; the cache keeps that from
    re-globbing and re-parsing every receipt each time.
    """
    now = time.time()
    dirs = {sideview_data_dir(), effective_sideview_data_dir()}
    if now - _KNOWN_IDS_CACHE["at"] < 10 and _KNOWN_IDS_CACHE["dirs"] == dirs:
        return _KNOWN_IDS_CACHE["ids"]
    ids = set()
    for base in dirs:
        try:
            with open(os.path.join(base, "side-sessions.jsonl"),
                      encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        sid = json.loads(line).get("id")
                    except Exception:
                        continue
                    if sid:
                        ids.add(str(sid))
        except OSError:
            pass
        for path in glob.glob(os.path.join(base, "receipts", "*", "receipt.json")):
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    sid = json.load(f).get("side_session_id")
                if sid:
                    ids.add(str(sid))
            except Exception:
                continue
    _KNOWN_IDS_CACHE.update({"at": now, "ids": ids, "dirs": dirs})
    return ids


def sideview_installed():
    """Whether wonder-margin (which now ships Sideview) is installed.

    Tips outlive their plugin if nothing checks: after an uninstall
    the box must go silent rather than display a ghost forever.
    Honours XDG_DATA_HOME like the rest of Muse's data layout.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    base = os.path.expanduser(xdg) if xdg else os.path.expanduser("~/.local/share")
    path = os.path.join(base, "muse", "plugins", "installed.json")
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            record = json.load(f).get("plugins", {}).get("wonder-margin")
    except Exception:
        return False
    return bool(record and record.get("enabled", True))


SIDEVIEW_CHARTER_MARK = ("You are Cyclops Sideview — a passive side view "
                         "of the builder's own work")
_SIDEVIEW_MARK_CACHE = {}


def _all_strings(value, depth=0):
    if depth > 12:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _all_strings(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            yield from _all_strings(v, depth + 1)


def is_sideview_session(path, known_ids=None):
    """Whether a session log belongs to a Cyclops Sideview session.

    Registered/receipted ids first. The fallback inspects only the
    session's own user-intent record for the exact charter opening —
    a builder that merely *read* Sideview's files (charter text inside
    tool results) is not a side session, and a side session is caught
    wherever in the head its prompt record lands.
    """
    sid = os.path.basename(os.path.dirname(path))
    if known_ids is None:
        known_ids = known_sideview_session_ids()
    if sid in known_ids:
        return True
    try:
        st = os.stat(path)
        cache_key = (st.st_mtime, st.st_size)
    except OSError:
        return False
    cached = _SIDEVIEW_MARK_CACHE.get(path)
    if cached and cached[0] == cache_key:
        return cached[1]
    marked = False
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            read = 0
            for line in f:
                read += len(line)
                if read > 2 * 1024 * 1024:
                    break
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("payload_type") == "runtime.user_intent.accepted":
                    # Only the FIRST user intent decides, and only
                    # when the charter is its opening — a builder who
                    # later quotes the charter is still a builder.
                    marked = any(s.lstrip().startswith(SIDEVIEW_CHARTER_MARK)
                                 for s in _all_strings(rec.get("payload")))
                    break
    except Exception:
        marked = False
    if len(_SIDEVIEW_MARK_CACHE) > 512:
        _SIDEVIEW_MARK_CACHE.clear()
    _SIDEVIEW_MARK_CACHE[path] = (cache_key, marked)
    return marked


def newest_session(base=None, exclude_sideview=True):
    base = base or os.path.expanduser("~/.local/share/muse/sessions")
    files = glob.glob(os.path.join(base, "*", "*", "*", "*", "session.jsonl"))
    known_ids = known_sideview_session_ids() if exclude_sideview else set()
    newest, newest_mtime = None, None
    for path in files:
        if exclude_sideview and is_sideview_session(path, known_ids):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue  # vanished between glob and stat; not the newest
        if newest_mtime is None or mtime > newest_mtime:
            newest, newest_mtime = path, mtime
    return newest

class Margin:
    def __init__(self, kept_path=None, sideview_path=None,
                 sideview_known_ids=None, sideview_installed=None):
        self.sigil, self.state, self.colour = "·", "resting", GREY
        self.notes = []          # (sigil, colour, text), newest last
        self.marks = 0           # events observed this session
        self.page_pos = 0        # where my mark sits on the page
        self.last_signal = time.time()
        self.session = "—"
        self.model = "—"         # unobserved until run.model.configured says so
        self.ended = False       # this session's end was observed (adoption gate)
        self._approval_open = False  # an approval ask was seen, not yet settled
        self._branches_open = 0      # subagent spawns seen, not yet back
        self._branch_labels = {}   # workflow child label -> starts not yet back (labels may repeat in parallel)
        self.active = {}         # effect/call id -> tool name, for honest returns
        self.pending = {}        # effect/call id -> start-note text, collapsed on return
        self.stamps = []         # mark times, newest last, for the rhythm row
        self.trail = []          # (page_pos, sigil, time), newest last: the comet's tail
        self.breathe = False     # approval-wait pulse phase; True only while genuinely waiting
        self.detail = ""         # what the mark is doing, e.g. the file it sits in
        self.state_since = time.time()  # when the current state began, for the live clock
        self._at = None          # host time of the record being fed, if it carried one
        # Deeds actually returned this session, tallied at the page foot.
        self.tally = {"read": 0, "edited": 0, "ran": 0, "branched": 0, "waited": 0}
        # A line kept: chosen on purpose (margin-keep), kept in a file so it
        # survives the session. The pane only ever reads it.
        self.kept_path = kept_path if kept_path is not None else os.path.expanduser(
            os.environ.get("MARGIN_KEPT") or KEPT_DEFAULT)
        self._kept_cache = (None, "")  # (mtime, text)
        # The side's latest word: Cyclops Sideview's tips log, read-only
        # here. It is a visitor's comment, never a mark: it earns no
        # tally stroke, no annotation, and no ✓.
        self.sideview_path = sideview_path if sideview_path is not None else os.path.expanduser(
            os.environ.get("MARGIN_SIDEVIEW_TIPS") or sideview_tips_default())
        self._sideview_cache = (None, "", None)  # (mtime, latest tip, created epoch)
        # Display provenance: only entries Sideview registered or
        # receipted may appear, and only while Sideview is installed.
        # None means "ask the real checks"; tests may inject both.
        self._side_known_ids = sideview_known_ids
        self._side_installed = sideview_installed
        self._side_path_explicit = (sideview_path is not None
                                    or bool(os.environ.get("MARGIN_SIDEVIEW_TIPS")))
        self._installed_cache = (0.0, False)  # (checked_at, result)
        # The last committed answer, held for the copy button. Held, never
        # rendered: the pane shows marks, the clipboard gets the words.
        self.last_answer = ""
        self.button = None       # (row, col0, col1) 0-based, set by render()
        self.copy_feedback = ""  # transient button label after a click
        self.copy_until = 0.0    # feedback shown until this time; never a mark
        # The Sideview toggle: a pane/session this margin opened, or
        # None. Opening/closing it is a pane-local act, never a mark.
        self.sideview_target = None  # tmux pane id ("%…") or session name
        self.sideview_kind = None    # "pane" | "session"
        self.side_button = None      # (row, col0, col1) 0-based
        self.side_feedback = ""      # transient side-button label
        self.side_until = 0.0
        # The side-log viewer: a pager pane this margin opened, or None.
        self.log_target = None
        self.log_kind = None         # "pane" | "session"
        self.log_button = None       # (row, col0, col1) 0-based
        self.log_feedback = ""
        self.log_until = 0.0
        self._side_entries_cache = (None, [], 0)  # (mtime, verified entries, size)
        self._side_count_cache = (None, 0)  # ((mtime, size, known), verified count)
        self.cwd = ""                # builder cwd from the host's route facts

    def kept_text(self):
        try:
            mtime = os.path.getmtime(self.kept_path)
        except OSError:
            return ""
        if self._kept_cache[0] != mtime:
            try:
                with open(self.kept_path, encoding="utf-8", errors="ignore") as f:
                    text = next((clean(ln.strip()) for ln in f if ln.strip()), "")
            except OSError:
                text = ""
            self._kept_cache = (mtime, text)
        return self._kept_cache[1]

    def _resolve_sideview_path(self):
        """Per-project resolution, re-run on every look.

        Explicit path (constructor/env) always wins. Otherwise the
        builder's cwd (from route facts) selects its project's log —
        and once the cwd is known, that project's log is the only
        source: falling back to the legacy global log would show
        another project's stale word as this project's side view.
        The global log is read only before the cwd is known (the
        first moments of a session). The active-data-dir pointer is
        honoured through effective_sideview_data_dir().
        """
        if self._side_path_explicit:
            return
        if self.cwd:
            chosen = project_tips_path(effective_sideview_data_dir(), self.cwd)
        else:
            chosen = sideview_tips_default()
        if chosen != self.sideview_path:
            self.sideview_path = chosen
            self._sideview_cache = (None, "", None)
            self._side_entries_cache = (None, [], 0)
            self._side_count_cache = (None, 0)

    def sideview_entry(self):
        """(latest tip text, created epoch|None), tail-read and cached.

        Provenance is enforced here, at the display layer: Sideview
        must still be installed, and the entry's session id must be
        one Sideview registered or receipted. A forged or orphaned
        entry is not displayed and not paraphrased — no box.
        """
        if not self._installed_cached():
            return "", None
        self._resolve_sideview_path()
        try:
            mtime = os.path.getmtime(self.sideview_path)
        except OSError:
            return "", None
        # No second cache here: _verified_sideview_entries already
        # caches on (mtime, known-id set), and a mtime-only cache at
        # this layer hid freshly-registered tips indefinitely.
        entries, size = self._verified_sideview_entries(mtime)
        entry = entries[-1] if entries else {"text": "", "created": None}
        if entry["text"]:
            return entry["text"], entry["created"]
        if size > SIDEVIEW_TAIL_BYTES:
            # The newest entry's header fell before the tail:
            # say so, rather than vanish silently.
            return ("(the latest side entry is larger than the "
                    "margin reads — full text in the tips log)"), None
        return "", None

    def _verified_sideview_entries(self, mtime=None):
        """(verified entries oldest-first, file size), tail-read, cached.

        Same gates as the box: installed + registered/receipted ids.
        """
        if mtime is None:
            try:
                mtime = os.path.getmtime(self.sideview_path)
            except OSError:
                return [], 0
        known = (self._side_known_ids if self._side_known_ids is not None
                 else known_sideview_session_ids())
        # The cache key includes the known-id set: an entry appended
        # just before its registration lands must become visible when
        # the id arrives, not only when the log's mtime next changes.
        cache_key = (mtime, frozenset(known))
        if self._side_entries_cache[0] == cache_key:
            return self._side_entries_cache[1], self._side_entries_cache[2]
        entries, size = [], 0
        try:
            with open(self.sideview_path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - SIDEVIEW_TAIL_BYTES))
                raw = f.read().decode("utf-8", "ignore")
            entries = [e for e in sideview_entries(raw)
                       if e["text"] and e.get("session") in known]
        except OSError:
            entries, size = [], 0
        self._side_entries_cache = (cache_key, entries, size)
        return entries, size

    def _installed_cached(self):
        if self._side_installed is not None:
            return self._side_installed
        checked_at, cached = self._installed_cache
        if time.time() - checked_at > 10:
            cached = sideview_installed()
            self._installed_cache = (time.time(), cached)
        return cached

    def sideview_count(self):
        """How many verified side entries exist (for the log button).

        Counts the whole log by streaming it line by line — the
        256 KiB tail that serves the latest tip would undercount a
        long log, and the button's number must be the real count.
        """
        if not self._installed_cached():
            return 0
        self._resolve_sideview_path()
        try:
            st = os.stat(self.sideview_path)
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            return 0
        known = (self._side_known_ids if self._side_known_ids is not None
                 else known_sideview_session_ids())
        cache_key = (mtime, size, frozenset(known))
        if self._side_count_cache[0] == cache_key:
            return self._side_count_cache[1]
        count = 0
        session, has_text, seen_body = None, False, False
        try:
            with open(self.sideview_path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = SIDEVIEW_HEADER_RE.match(line.rstrip("\n"))
                    if m:
                        if session in known and has_text:
                            count += 1
                        session, has_text, seen_body = m.group(2), False, False
                        continue
                    if session is None:
                        continue
                    body = line[2:] if line.startswith("> ") else line.rstrip("\n")
                    if not seen_body:
                        if not body.strip():
                            continue
                        seen_body = True
                        if body.startswith("Watched:"):
                            continue
                    if _sideview_display_line(body).strip():
                        has_text = True
            if session in known and has_text:
                count += 1
        except OSError:
            count = 0
        self._side_count_cache = (cache_key, count)
        return count

    def sideview_tip(self):
        return self.sideview_entry()[0]

    def _now(self):
        return self._at if self._at is not None else time.time()

    def note(self, sigil, colour, text):
        text = clean(text)
        # An identical consecutive note is displayed once (parallel calls to
        # the same file read as one mark on the page) — but the event was
        # still observed, so it still counts below.
        if not (self.notes and self.notes[-1][2] == text):
            self.notes.append((sigil, colour, text))
            self.notes = self.notes[-5:]
        self.marks += 1
        self.page_pos += 1
        self.last_signal = self._now()
        self.stamps.append(self.last_signal)
        self.stamps = self.stamps[-720:]
        self.trail.append((self.page_pos, sigil, self.last_signal))
        self.trail = self.trail[-24:]

    def set(self, sigil, state, colour, detail=""):
        self.sigil, self.colour = sigil, colour
        # State text can carry host fields (e.g. the session-end reason):
        # it is rendered, so it is cleaned like every other host string.
        self.state = clean(state)
        self.detail = clean(detail)
        self.state_since = self._now()

    def feed(self, rec):
        if not isinstance(rec, dict):
            return
        self._at = event_time(rec)
        pt = rec.get("payload_type") or ""
        pl = _as_dict(rec.get("payload"))
        ev = _as_dict(pl.get("event"))
        kind = ev.get("kind") or pl.get("kind") or ""
        if not isinstance(kind, str):
            kind = str(kind)
        if pt == "session.started":
            sid = _as_dict(rec.get("stream")).get("id", "")
            self.session = clean(str(sid)[:8]) if sid else self.session
            self.set("·", "resting", GREY); self.note("·", GREY, "session opened — present, nothing claimed")
        elif pt == "session.end":
            reason = _as_dict(pl.get("record")).get("exit_reason") or "ended"
            self.ended = True
            self.set("·", f"ended ({reason})", GREY)
            self.note("·", GREY, f"session ended ({reason}) — marks left as they stand")
        elif pt == "runtime.session.route_facts":
            cwd = _as_dict(pl.get("record")).get("cwd")
            if isinstance(cwd, str) and cwd:
                self.cwd = cwd
        elif pt == "run.model.configured":
            label = _as_dict(pl.get("record")).get("display_label")
            if label: self.model = clean(label)
        elif pt == "runtime.user_intent.accepted":
            self.set("›", "attending", INK); self.note("›", INK, "prompt received (text never shown here)")
        elif pt == "approval_wait.effect.started":
            tool = _as_dict(pl.get("record")).get("tool_name", "a tool")
            self._approval_open = True
            self.set("?", "waiting for approval", AMBER); self.note("?", AMBER, f"approval asked — {tool} held")
        elif pt == "approval_wait.effect.terminal":
            # The tally counts deeds that returned; the wait returns here,
            # not when it was asked — and only a wait actually seen asked
            # earns the stroke (a pane opened mid-approval saw no wait).
            if self._approval_open:
                self.tally["waited"] += 1
                self._approval_open = False
            outcome = _as_dict(_as_dict(pl.get("record")).get("outcome")).get("kind", "settled")
            self.set("›", "attending", INK); self.note("›", INK, f"approval {outcome}")
        elif pt == "subagent.control.spawn_accepted":
            self._branches_open += 1
            self.set("⌥", "branching", INK); self.note("⌥", INK, "branch opened — a subagent steps out")
        elif pt == "subagent.control.result_ready":
            if self._branches_open:
                self.tally["branched"] += 1
                self._branches_open -= 1
            self.note("⌥", GREY, "branch back — subagent result ready")
        elif kind == "workflow_child_lifecycle":
            # Only the edges are marks; usage/terminal bookkeeping is not.
            # Labels are counted, not just seen: parallel children may
            # share one label, and each return is a branch back.
            label = clean(ev.get("label") or "workflow child")
            if ev.get("status") == "started":
                self._branch_labels[label] = self._branch_labels.get(label, 0) + 1
                self.set("⌥", "branching", INK, detail=label)
                self.note("⌥", INK, f"branch — {label}")
            elif ev.get("status") == "completed":
                if self._branch_labels.get(label):
                    self.tally["branched"] += 1
                    self._branch_labels[label] -= 1
                    if not self._branch_labels[label]:
                        del self._branch_labels[label]
                self.note("⌥", GREY, f"branch back — {label}")
        elif kind == "context_compaction_installed":
            # A candidate is not a fold. Only the installed fold is claimed,
            # and nothing is claimed about what it kept or lost.
            self.set("¦", "folded — context compacted", GREY)
            self.note("¦", GREY, "fold — context compacted; contents not claimed")
        elif pt == "tool_batch.effect.started":
            r0 = _as_dict(pl.get("record"))
            tool = r0.get("tool_name", "tool")
            if not isinstance(tool, str):
                tool = str(tool)
            if tool in READ_TOOLS:
                verb, sigil = "reading", "§"
            elif tool in EDIT_TOOLS:
                verb, sigil = "editing", "✎"
            elif tool in BRANCH_TOOLS:
                verb, sigil = "branching", "⌥"
            elif tool in WATCH_TOOLS:
                verb, sigil = "watching", "~"
            else:
                verb, sigil = "working", "~"
            # The read head names the file the host logged. The log carries
            # no line number, so no file:line is shown — never invented.
            short = subject_short(r0, tool)
            text = f"{verb} — {short}"
            for key in (r0.get("effect_id"), r0.get("call_id")):
                if key and isinstance(key, (str, int)):
                    self.active[key] = tool
                    self.pending[key] = (text, verb, short)
            self.set(sigil, verb, INK, detail=short); self.note(sigil, INK, text)
        elif pt == "tool_batch.effect.terminal":
            r = _as_dict(pl.get("record"))
            keys = [r.get("effect_id"), r.get("call_id")]
            # Both id keys are always retired, tool_name or not: leaving one
            # behind leaks an entry per tool call for the pane's whole life.
            tool = r.get("tool_name")
            started = verb = short = None
            for key in keys:
                if not key or not isinstance(key, (str, int)):
                    continue
                known = self.active.pop(key, None)
                if tool is None:
                    tool = known
                if key in self.pending:
                    started, verb, short = self.pending.pop(key)
            tool = tool or "tool"
            if not isinstance(tool, str):
                tool = str(tool)
            observed = started is not None  # a start was actually seen
            out = _as_dict(r.get("outcome"))
            outcome = str(out.get("kind") or "returned").lower()
            # The honest verdict can hide one level down: a "completed"
            # wrapper around a failed/cancelled terminal is still a
            # failure/interrupt, and is reported as one.
            nested = str(_as_dict(_as_dict(out.get("task_completion")).get("terminal")).get("kind") or "").lower()
            # Retire the start note only when no sibling call with the same
            # text is still running (parallel calls share one display note).
            if started and not any(v[0] == started for v in self.pending.values()):
                self.notes = [n for n in self.notes if n[2] != started]
            disp = tool.rsplit("__", 1)[-1] if tool.startswith("mcp__") else tool
            failed = ("fail" in outcome or "error" in outcome
                      or nested in ("failed", "failure", "error"))
            stopped = (outcome in ("cancelled", "canceled", "interrupted")
                       or nested in ("cancelled", "canceled", "interrupted"))
            if failed:
                shown = nested if outcome == "completed" and nested else outcome
                self.set("!", "a tool reported a problem", RED); self.note("!", RED, f"{disp} came back wrong: {shown}")
            elif stopped:
                shown = nested if outcome == "completed" and nested else outcome
                self.set("—", "interrupted", AMBER); self.note("—", AMBER, f"{disp} interrupted ({shown})")
            elif not observed:
                # A terminal whose start was never seen (the tail window cut
                # between them) proves a return, not a deed: no tally stroke
                # is invented for work the pane did not watch begin.
                self.note("~", GREY, f"{disp} returned ({outcome})")
            elif outcome != "completed":
                # An allowlist, not a denylist: only `completed` is a clean
                # return. Anything else (timeout, aborted, denied, …) is
                # noted literally and earns no stroke — an unknown outcome
                # must never be laundered into a deed by not matching a
                # failure list.
                self.note("~", GREY, f"{disp} returned ({outcome})")
                if not self.pending:
                    self.set("›", "attending", INK)
            else:
                # A return is a return — never a success verdict. It replaces
                # its start note, so one tool leaves one line, not two. Each
                # kind of work gets its own closing voice; the outcome in
                # brackets stays literal, never dressed up. Only a clean
                # return of an observed start earns a tally stroke — and the
                # mark moves off the finished deed instead of ticking on it.
                if verb == "reading":
                    self.tally["read"] += 1
                    self.note("§", GREY, f"{short or tool} closed ({outcome})")
                elif verb == "editing":
                    self.tally["edited"] += 1
                    self.note("✎", GREY, f"{short or tool} marked ({outcome})")
                elif verb == "branching":
                    # The spawn call returning only opens the branch; the
                    # branch itself returns via result_ready / workflow-child
                    # completion. Counting both would count one branch twice.
                    self.note("⌥", GREY, f"branch call back ({outcome})")
                elif verb == "watching":
                    self.note("~", GREY, f"{disp} watch ended ({outcome})")
                else:
                    self.tally["ran"] += 1
                    self.note("~", GREY, f"{disp} back ({outcome})")
                if not self.pending:
                    self.set("›", "attending", INK)
        elif pt == "runtime.session" and ev.get("operation") == "model.meta.response" and kind in ("side_effect_intent", "scheduled", "started"):
            # The host declares a model call with side_effect_intent /
            # operation=model.meta.response (verified against real logs);
            # scheduled/started are kept for the shape this branch was
            # written against, should the host return to it.
            self.set("›", "responding", INK)
        elif kind == "assistant_message_committed":
            text = ev.get("text")
            if isinstance(text, str) and text.strip():
                self.last_answer = text
            self.set("·", "resting — answer held in the main pane", GREY)
            self.note("·", GREY, "answer committed; back to stillness")
        self._at = None

def deliver_copy(text, emit):
    """Hand `text` to a clipboard. Returns "copied" only when a local
    clipboard tool exited cleanly (checked), else "sent" after emitting
    OSC52 — the terminal/tmux may honour it, but nothing confirms back,
    so the button may never claim more than that."""
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"], ["pbcopy"]):
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            subprocess.run([exe] + cmd[1:], input=text.encode(), timeout=5,
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return "copied"
        except Exception:
            pass
    payload = base64.b64encode(text.encode()).decode()
    emit(f"\033]52;c;{payload}\a")
    return "sent"


def do_copy(m, deliver=None, emit=None):
    """The button, pressed. Feedback lives on the button for a few seconds
    and nowhere else: a click is a pane-local act, never a host mark."""
    if not m.last_answer:
        m.copy_feedback, m.copy_until = "⧉ nothing yet", time.time() + 2.5
        return "nothing"
    deliver = deliver or deliver_copy
    emit = emit or (lambda s: (sys.stdout.write(s), sys.stdout.flush()))
    outcome = deliver(m.last_answer, emit)
    m.copy_feedback = "⧉ copied" if outcome == "copied" else "⧉ copy sent"
    m.copy_until = time.time() + 2.5
    return outcome


SIDEVIEW_TOPIC = ("Watch this work from the side. "
                  "Leave a tip only if something is genuinely relevant.")


def sideview_bin():
    """The muse-sideview launcher, if Sideview is installed."""
    override = os.environ.get("MARGIN_SIDEVIEW_BIN")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override
    found = shutil.which("muse-sideview")
    if found:
        return found
    fallback = os.path.expanduser("~/.local/bin/muse-sideview")
    return fallback if os.path.isfile(fallback) and os.access(fallback, os.X_OK) else None


def _tmux(runner, *argv):
    return runner(["tmux", *argv], capture_output=True, text=True, timeout=10)


def sideview_alive(m, runner=subprocess.run):
    if not m.sideview_target:
        return False
    try:
        if m.sideview_kind == "pane":
            proc = _tmux(runner, "display-message", "-p", "-t",
                         m.sideview_target, "#{pane_id}")
        else:
            proc = _tmux(runner, "has-session", "-t", m.sideview_target)
        return proc.returncode == 0
    except Exception:
        return False


def toggle_sideview(m, runner=subprocess.run):
    """The side-view button, pressed: open the visitor, or close it.

    Opening launches `muse-sideview` in its own tmux pane (split when
    inside tmux, a detached session otherwise) watching the builder's
    cwd. Closing kills only the pane/session this margin opened.
    Returns "on" | "off" | "missing" | "failed". Never a host mark.
    """
    import shlex
    if m.sideview_target:
        if sideview_alive(m, runner):
            try:
                if m.sideview_kind == "pane":
                    _tmux(runner, "kill-pane", "-t", m.sideview_target)
                else:
                    _tmux(runner, "kill-session", "-t", m.sideview_target)
            except Exception:
                pass
            m.sideview_target = m.sideview_kind = None
            m.side_feedback, m.side_until = "◐ side view: off", time.time() + 2.5
            return "off"
        m.sideview_target = m.sideview_kind = None  # it closed itself; reopen below
    binary = sideview_bin()
    if not binary:
        m.side_feedback = "◐ muse-sideview not found"
        m.side_until = time.time() + 3.5
        return "missing"
    cwd = m.cwd or os.getcwd()
    # The button opens the separate Sideview conversation in its own
    # pane (the passive watcher stays available as muse-sideview
    # --watch from a terminal; it is not what this button does).
    inner = f"{shlex.quote(binary)} {shlex.quote(SIDEVIEW_TOPIC)}"
    try:
        if os.environ.get("TMUX"):
            proc = _tmux(runner, "split-window", "-h", "-P", "-F",
                         "#{pane_id}", "-c", cwd, inner)
            if proc.returncode != 0 or not proc.stdout.strip():
                raise RuntimeError("split failed")
            m.sideview_target, m.sideview_kind = proc.stdout.strip(), "pane"
        else:
            name = f"margin-sideview-{os.getpid()}"
            proc = _tmux(runner, "new-session", "-d", "-s", name, "-c", cwd, inner)
            if proc.returncode != 0:
                raise RuntimeError("session failed")
            m.sideview_target, m.sideview_kind = name, "session"
    except Exception:
        m.side_feedback = "◐ side view: could not open"
        m.side_until = time.time() + 3.5
        return "failed"
    m.side_feedback, m.side_until = "◐ side view: on", time.time() + 2.5
    return "on"


def toggle_side_log(m, runner=subprocess.run):
    """The side-log button: open the whole tips log in a pager pane.

    The box only ever shows the latest tip; this is how the earlier
    ones are read. Opens `less`/`more` on the tips file in its own
    tmux pane (detached session outside tmux); pressing again closes
    only that pane. Returns "open" | "closed" | "empty" | "failed".
    """
    import shlex
    if m.log_target:
        alive = False
        try:
            if m.log_kind == "pane":
                alive = _tmux(runner, "display-message", "-p", "-t",
                              m.log_target, "#{pane_id}").returncode == 0
            else:
                alive = _tmux(runner, "has-session", "-t",
                              m.log_target).returncode == 0
        except Exception:
            alive = False
        if alive:
            try:
                if m.log_kind == "pane":
                    _tmux(runner, "kill-pane", "-t", m.log_target)
                else:
                    _tmux(runner, "kill-session", "-t", m.log_target)
            except Exception:
                pass
            m.log_target = m.log_kind = None
            m.log_feedback, m.log_until = "≡ side log: closed", time.time() + 2.5
            return "closed"
        m.log_target = m.log_kind = None
    if not m.sideview_count():
        m.log_feedback, m.log_until = "≡ side log · none yet", time.time() + 3.0
        return "empty"
    pager = shutil.which("less") or shutil.which("more") or "cat"
    inner = f"{shlex.quote(pager)} {shlex.quote(m.sideview_path)}"
    cwd = m.cwd or os.getcwd()
    try:
        if os.environ.get("TMUX"):
            proc = _tmux(runner, "split-window", "-h", "-P", "-F",
                         "#{pane_id}", "-c", cwd, inner)
            if proc.returncode != 0 or not proc.stdout.strip():
                raise RuntimeError("split failed")
            m.log_target, m.log_kind = proc.stdout.strip(), "pane"
        else:
            name = f"margin-sidelog-{os.getpid()}"
            proc = _tmux(runner, "new-session", "-d", "-s", name, "-c", cwd, inner)
            if proc.returncode != 0:
                raise RuntimeError("session failed")
            m.log_target, m.log_kind = name, "session"
    except Exception:
        m.log_feedback = "≡ side log: could not open"
        m.log_until = time.time() + 3.5
        return "failed"
    m.log_feedback, m.log_until = "≡ side log: open", time.time() + 2.5
    return "open"


def parse_input(data):
    """Terminal input -> intent. SGR mouse presses (not releases, not
    motion); a lone `c`/`y` copies, lone Ctrl-C / `q` leaves. 1-based cells.

    Everything else is inert: escape sequences (arrow keys carry a literal
    `C`) are stripped whole, bracketed-paste content is dropped whole, and
    a multi-character burst is text, not keys — pasting a sentence that
    happens to contain c or q must never copy or quit.
    """
    events = []
    for b, x, y, final in MOUSE_RE.findall(data):
        code = int(b)
        # Wheel events (64/65) are scrolls, never presses: scrolling
        # over a button must not copy, open the log, or launch a
        # side session nobody asked for.
        if code & 64:
            continue
        if final == "M" and not (code & 32) and code & 3 != 3:
            events.append(("click", int(x), int(y)))
    rest = MOUSE_RE.sub("", data)
    rest = PASTE_RE.sub("", rest)
    rest = CSI_RE.sub("", rest)
    rest = ESC_RE.sub("", rest)
    if len(rest) == 1:
        if rest in "cCyY":
            events.append(("copy",))
        elif rest in "vV":
            events.append(("sideview",))
        elif rest in "lL":
            events.append(("sidelog",))
        elif rest in ("\x03", "q", "Q"):
            events.append(("quit",))
    return events


def hit_button(m, x, y):
    """1-based terminal cell against the last rendered button geometry."""
    if not m.button:
        return False
    row, col0, col1 = m.button
    return y - 1 == row and col0 <= x - 1 <= col1


def hit_side_button(m, x, y):
    if not m.side_button:
        return False
    row, col0, col1 = m.side_button
    return y - 1 == row and col0 <= x - 1 <= col1


def hit_log_button(m, x, y):
    if not m.log_button:
        return False
    row, col0, col1 = m.log_button
    return y - 1 == row and col0 <= x - 1 <= col1


def tally_text(m, width=42):
    # The tally shortens gracefully — prefix, then words, then bare counts —
    # rather than ever being clipped mid-word at the pane edge.
    keys = ("read", "edited", "ran", "branched", "waited")
    words = [f"{s} {w} {m.tally[k]}" for s, w, k in
             zip("§✎~⌥?", keys, keys) if m.tally[k]]
    if not words:
        return ""
    full = "this session · " + " · ".join(words)
    if len(full) + 1 <= width:
        return full
    bare = " · ".join(words)
    if len(bare) + 1 <= width:
        return bare
    return " · ".join(f"{s}{m.tally[k]}" for s, k in zip("§✎~⌥?", keys) if m.tally[k])


def render(m, width, height):
    width = max(10, width)
    # Short panes (the --top running head) get the compact form: fewer page
    # rows, the kept line on one line, the last two annotations — but the
    # status line is never the thing truncated away.
    compact = height <= 18
    page_rows = 3 if compact else max(6, min(18, height - 25))
    age = int(time.time() - m.last_signal)
    stale = age > 300
    sigil, colour, state = (m.sigil, m.colour, m.state)
    if stale and m.marks:
        state, colour = state + " · last signal old", GREY
    lines = []
    # The margin-mark, worn in the header: a graphite rule with one tick,
    # crossed by the title it measures. The tick stays graphite like the
    # rest of the rule — except when the head mark is one that needs eyes
    # (approval asked, or a tool came back wrong), when it goes red: the
    # one red reading, marking what matters. Never decoration.
    needs_eyes = sigil in ("?", "!")
    tick = f"{RED}━━{RESET}" if needs_eyes else f"{GREY}──{RESET}"
    lines.append(f"   {GREY}│{RESET}   {INK}WONDER{RESET} {GREY}· in the margin{RESET}")
    lines.append(f"   {GREY}│{tick} {DIM}{m.model} · session {m.session} · {m.marks} marks observed{RESET}")
    if not compact:
        lines.append("")
    pos = m.page_pos % page_rows if page_rows else 0
    now = time.time()
    # The comet's tail: past marks cooling where they stood — on this page
    # only. When the mark wraps, the page has turned; older echoes do not
    # bleed through from the page before. Newest echo per row wins; the
    # head row is never overwritten. Fading is by real age.
    echoes = {}
    page_base = m.page_pos - pos
    for idx, sg, t in m.trail:
        if page_base <= idx < m.page_pos:
            echoes[idx - page_base] = (sg, now - t)
    for i in range(page_rows):
        # The page fills as the mark descends: solid where it has been,
        # dotted where it has not. Honest position, not decoration.
        rule = ("─" if (m.marks and i <= pos) else "┄") * max(8, width - 12)
        if i == pos:
            tag = f" {m.state}" + (f" — {m.detail}" if m.detail else "")
            lines.append(f"   {colour}│{sigil}{tag}{RESET} {colour}{rule}{RESET}")
        elif i in echoes:
            sg, echo_age = echoes[i]
            fade = GREY if echo_age < 10 else DIM
            lines.append(f"   {fade}│{sg}{RESET}  {DIM}{rule}{RESET}")
        else:
            lines.append(f"   {GREY}│{RESET}  {DIM}{rule}{RESET}")
    if not compact:
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
    tally = tally_text(m, width)
    if tally:
        lines.append(f" {DIM}{tally}{RESET}")
    # The one button in the margin: copies the last committed answer.
    # Ink when there is something to copy, dim when there is not, reversed
    # while its brief feedback shows. Geometry is recorded for mouse hits.
    if time.time() < m.copy_until and m.copy_feedback:
        label, btn_colour = m.copy_feedback, REV + INK
    elif m.last_answer:
        label, btn_colour = "⧉ copy my last message", INK
    else:
        label, btn_colour = "⧉ copy my last message · none yet", DIM
    btn = f"[ {label} ]"
    hint = f" {DIM}(click or c){RESET}" if 1 + len(btn) + 13 <= width else ""
    lines.append(f" {btn_colour}{btn}{RESET}{hint}")
    # Hit-box matches what is actually drawn: the line is clipped to the
    # pane width below, so the box ends at the clipped edge, never past it.
    drawn = clip(lines[-1], width)
    m.button = (len(lines) - 1, 1,
                max(1, min(display_width(btn), display_width(drawn) - 1)))
    # The second button: the Sideview toggle. Ink while the visitor is
    # open, dim while not, reversed during its brief feedback. Click
    # it (or press v) to open/close the live side pane.
    if time.time() < m.side_until and m.side_feedback:
        side_label, side_colour = m.side_feedback, REV + INK
    elif m.sideview_target:
        side_label, side_colour = "◐ Side Review: open", INK
    else:
        side_label, side_colour = "◐ Open Side Review Conversation", DIM
    side_btn = f"[ {side_label} ]"
    side_hint = f" {DIM}(click or v){RESET}" if 1 + len(side_btn) + 13 <= width else ""
    lines.append(f" {side_colour}{side_btn}{RESET}{side_hint}")
    side_drawn = clip(lines[-1], width)
    m.side_button = (len(lines) - 1, 1,
                     max(1, min(display_width(side_btn), display_width(side_drawn) - 1)))
    # The third button: read the whole side log, not just the latest.
    # Its label carries the verified entry count, so an hour's worth
    # of tips never silently collapses to the newest one.
    if time.time() < m.log_until and m.log_feedback:
        log_label, log_colour = m.log_feedback, REV + INK
    elif m.log_target:
        log_label, log_colour = "≡ side log: open", INK
    else:
        count = m.sideview_count()
        log_label = f"≡ side log · {count}" if count else "≡ side log · none yet"
        log_colour = INK if count else DIM
    log_btn = f"[ {log_label} ]"
    log_hint = f" {DIM}(click or l){RESET}" if 1 + len(log_btn) + 13 <= width else ""
    lines.append(f" {log_colour}{log_btn}{RESET}{log_hint}")
    log_drawn = clip(lines[-1], width)
    m.log_button = (len(lines) - 1, 1,
                    max(1, min(display_width(log_btn), display_width(log_drawn) - 1)))
    # A line kept is kept on purpose, in a file, across sessions
    # (margin-keep). No file, no box — the newest note is not dressed up
    # as something cherished.
    kept = m.kept_text()
    if kept and compact:
        lines.append(f" {GREY}kept ·{RESET} “{kept}”")
    elif kept:
        box_w = max(20, width - 6)
        inner = ("“" + kept + "”")[:box_w]
        lines.append("")
        lines.append(clip(f" {GREY}╭─ a line kept {'─' * max(0, box_w - 14)}╮{RESET}", width))
        lines.append(f" {GREY}│{RESET} {inner}")
        lines.append(clip(f" {GREY}╰{'─' * box_w}╯{RESET}", width))
    if not compact:
        lines.append("")
    lines.append(f" {GREY}── annotations (newest last) ──{RESET}")
    for s, c, text in (m.notes[-2:] if compact else m.notes):
        lines.append(f"  {c}│{s}{RESET} {text}")
    # From the side: Cyclops Sideview's latest tip, shown as a visitor's
    # comment below the annotations. Attributed, wrapped, and never a
    # mark — it is not added to the annotations, earns no tally stroke,
    # and (cleaned on the way in) may not borrow the earned ✓. No tips
    # log, no box. It sits last so a short frame sacrifices the visitor
    # before it sacrifices the record.
    side, side_created = m.sideview_entry()
    side_start = None
    if side:
        if side_created is None:
            age_label, side_stale = "undated", False
        else:
            age_s = max(0, int(now - side_created))
            side_stale = age_s > 300
            if age_s < 60:
                age_label = "just now"
            elif age_s < 3600:
                age_label = f"{age_s // 60}m old"
            elif age_s < 86400:
                age_label = f"{age_s // 3600}h old"
            else:
                age_label = f"{age_s // 86400}d old"
        side_colour = DIM if side_stale else GREY
        if compact:
            side_start = len(lines)
            first = side.splitlines()[0] if side.splitlines() else ""
            more = " …" if ("\n" in side or len(first) < len(side)) else ""
            lines.append(f" {side_colour}◐ side · {age_label} ·{RESET} “{first}”{more}")
        else:
            box_w = max(20, width - 6)
            side_start = len(lines)
            lines.append("")
            title = f"from the side · Sideview · {age_label}"
            lines.append(clip(f" {side_colour}╭─ {title} {'─' * max(0, box_w - len(title) - 3)}╮{RESET}", width))
            wrapped = wrap_text(side, box_w)
            shown = wrapped[:6]
            if len(wrapped) > 6:
                shown = wrapped[:5] + [f"… +{len(wrapped) - 5} more lines (full tip in tips log)"]
            for wrapped_line in shown:
                lines.append(f" {side_colour}│{RESET} {wrapped_line}")
            lines.append(clip(f" {side_colour}╰{'─' * box_w}╯{RESET}", width))
    if not compact:
        lines.append("")
    lines.append(f" {DIM}talk in Muse pane → · Ctrl-C ends me{RESET}")
    # A box that does not fit whole is dropped whole, never amputated:
    # a half-drawn box would present a partial tip as the complete tip.
    if side_start is not None and len(lines) > height:
        if compact:
            del lines[side_start:side_start + 1]
        elif side_start < height:
            # Box spans from its leading blank to the closing border,
            # which sits just before the trailing blank+footer pair.
            del lines[side_start:len(lines) - 2]
    return "\n".join(clip(line, width) for line in lines[:height])

def term_size():
    try:
        s = os.get_terminal_size()
        return s.columns, s.lines
    except OSError:
        return 48, 44

def load_tail(m, path):
    """Feed the tail and return the byte offset actually consumed.

    The caller follows from this offset, not from a later getsize():
    anything written between the read and a size check would be skipped.
    Returns 0 when the log cannot be read.
    """
    m.session = clean(os.path.basename(os.path.dirname(path))[:8]) or m.session
    try:
        # Bounded tail: read at most the last 2 MB, never the whole log —
        # a multi-hundred-MB session must not spike the pane's memory.
        with open(path, encoding="utf-8", errors="ignore") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2_000_000))
            data = f.read()
            offset = f.tell()
        lines = data.splitlines()
        if size > 2_000_000 and lines:
            lines = lines[1:]  # the first line may be cut mid-record
        for line in lines[-3000:]:
            try: m.feed(json.loads(line))
            except Exception: pass
        m.page_pos = max(0, m.marks - 1)
        return offset
    except OSError:
        return 0


def feed_buffer(m, chunk, carry=""):
    """Feed complete log lines from `chunk`; return the unterminated rest.

    A line caught mid-write is held in the carry, never parsed half and
    dropped: its event still arrives when the write completes.
    """
    data = carry + chunk
    lines = data.split("\n")
    for line in lines[:-1]:
        if line.strip():
            try: m.feed(json.loads(line))
            except Exception: pass
    return "" if data.endswith("\n") else lines[-1]


def should_adopt(current_ended, current_age_s, newer_age_s):
    """Whether the pane may leave its session for a newer one.

    A live session is never stolen: two concurrent `muse` sessions would
    otherwise flip the pane between them, discarding its tally and held
    answer on every switch. Adoption needs the current session ended, or
    quiet for 30s while the other is active — long enough that two live
    sessions never trade places, short enough that a fresh launch does
    not sit with the previous session's corpse for five minutes.
    """
    if current_ended:
        return True
    return current_age_s > 30 and newer_age_s < current_age_s

def wait_for_session(pinned_path=None):
    """Wait for a session log to appear; return its path or None.

    `muse-margin` starts Muse and this pane at the same moment, so on a
    fresh install (or a cleaned sessions dir) no log exists yet when the
    pane starts. Exiting there would leave a marginless session with no
    warning; waiting is the honest behaviour for the live pane.
    """
    announced = False
    try:
        while True:
            if pinned_path:
                path = pinned_path if os.path.exists(pinned_path) else None
            else:
                path = newest_session()
            if path and os.path.exists(path):
                return path
            if not announced:
                sys.stdout.write("· Waiting for a Muse session log… (Ctrl-C ends me)\n")
                sys.stdout.flush()
                announced = True
            time.sleep(0.5)
    except KeyboardInterrupt:
        return None


def follow(path, once=False, pinned=False):
    # SIGTERM/SIGHUP must restore the terminal like Ctrl-C does:
    # Python's default kill would skip the finally and leave a
    # standalone terminal in cbreak with mouse reporting on.
    import signal as _signal
    def _leave(signum, frame):
        raise KeyboardInterrupt
    for _sig in (_signal.SIGTERM, _signal.SIGHUP):
        try:
            _signal.signal(_sig, _leave)
        except Exception:
            pass
    m = Margin()
    # Populate from the tail so a pane opened mid-session is not empty.
    # The follow offset is what the tail read consumed — never a later
    # getsize(), which would skip events written in between.
    offset = load_tail(m, path)
    if once:
        cols, rows = term_size()
        sys.stdout.write(render(m, cols, rows) + "\n")
        return
    sys.stdout.write("\033[?25l\033[2J")
    last_draw = ""
    carry = ""  # trailing partial log line, held until its write completes
    last_check = 0.0
    last_breathe = 0.0
    # A real terminal gets a clickable button (SGR mouse) and keys; a pipe
    # gets exactly the old behaviour. The terminal is always restored.
    interactive = bool(termios and sys.stdin.isatty() and sys.stdout.isatty())
    old_tty = None
    if interactive:
        try:
            old_tty = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            # Mouse + bracketed paste: paste arrives wrapped, so its text
            # can be dropped whole instead of read as keystrokes.
            sys.stdout.write("\033[?1000h\033[?1006h\033[?2004h")
            sys.stdout.flush()
        except Exception:
            interactive, old_tty = False, None
    try:
        while True:
            # Unless pinned to one log, adopt a newer session when one starts
            # (the pane is usually launched at the same moment as `muse`) —
            # but never steal a live session: a second concurrent `muse`
            # must not flip the pane back and forth, dropping its tally.
            if not pinned and time.time() - last_check > 10:
                last_check = time.time()
                newer = newest_session()
                if newer and newer != path:
                    try:
                        ages = (time.time() - os.path.getmtime(path),
                                time.time() - os.path.getmtime(newer))
                    except OSError:
                        ages = (0.0, 0.0)
                    if should_adopt(m.ended, ages[0], ages[1]):
                        path = newer
                        keep_target, keep_kind, keep_cwd = (
                            m.sideview_target, m.sideview_kind, m.cwd)
                        keep_log, keep_log_kind = m.log_target, m.log_kind
                        m = Margin()
                        # The visitor survives adoption: it watches the
                        # work, not one session log.
                        m.sideview_target, m.sideview_kind, m.cwd = (
                            keep_target, keep_kind, keep_cwd)
                        m.log_target, m.log_kind = keep_log, keep_log_kind
                        offset = load_tail(m, path)
                        carry = ""
            try:
                cols, rows = term_size()
                # A truncated/rotated log must not strand the pane past
                # EOF forever: start again at the top of the new file.
                try:
                    if os.path.getsize(path) < offset:
                        offset, carry = 0, ""
                except OSError:
                    pass
                with open(path, encoding="utf-8", errors="ignore") as f:
                    f.seek(offset)
                    chunk = f.read()
                    offset = f.tell()
                carry = feed_buffer(m, chunk, carry)
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
            if interactive:
                ready, _, _ = select.select([sys.stdin], [], [], 0.25)
                if ready:
                    data = os.read(sys.stdin.fileno(), 4096).decode("utf-8", "ignore")
                    for event in parse_input(data):
                        if event[0] == "quit":
                            raise KeyboardInterrupt
                        if event[0] == "copy" or (
                                event[0] == "click" and hit_button(m, event[1], event[2])):
                            do_copy(m)
                            last_draw = ""  # show the pressed button at once
                        if event[0] == "sideview" or (
                                event[0] == "click" and hit_side_button(m, event[1], event[2])):
                            toggle_sideview(m)
                            last_draw = ""  # show the toggle at once
                        if event[0] == "sidelog" or (
                                event[0] == "click" and hit_log_button(m, event[1], event[2])):
                            toggle_side_log(m)
                            last_draw = ""
            else:
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        if interactive:
            sys.stdout.write("\033[?2004l\033[?1006l\033[?1000l")
        if old_tty is not None:
            try: termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_tty)
            except Exception: pass
        sys.stdout.write(f"\033[?25h\n{GREY}· Wonder has left the margin.{RESET}\n")

def main():
    ap = argparse.ArgumentParser(description="Wonder in the Margin — Muse sidecar pane")
    ap.add_argument("--session", help="session.jsonl to watch (default: newest live session)")
    ap.add_argument("--once", action="store_true", help="draw one frame and exit")
    args = ap.parse_args()
    path = args.session or newest_session()
    if not path or not os.path.exists(path):
        if args.once:
            print("· No Muse session log found yet — start `muse` first, then run me.")
            return 1
        # Live pane: Muse may still be starting (muse-margin launches
        # both together). Wait for the first log instead of dying.
        path = wait_for_session(pinned_path=args.session)
        if not path:
            return 0
    follow(path, once=args.once, pinned=bool(args.session))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
