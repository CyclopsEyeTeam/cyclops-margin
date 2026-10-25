"""Focused tests for the Wonder margin sidecar.

Run: python3 -m unittest discover -s tests -v
Covers: one-frame rendering from a session log, honest tool returns,
no prompt text shown, waiting-on-approval state, and live following
when stdout is not a TTY (the pane must not crash for lack of a
terminal size).
"""
import importlib.util, json, os, re, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "sidecar", "margin.py")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def rec(pt, payload, recorded_at=None):
    row = {"payload_type": pt, "payload": payload,
           "stream": {"id": "deadbeef-1234"}}
    if recorded_at is not None:
        row["recorded_at"] = recorded_at
    return json.dumps(row)


def plain(text):
    return ANSI.sub("", text)


class MarginSidecarTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.dir.name, "session.jsonl")
        rows = [
            rec("session.started", {"kind": "session_started"}),
            rec("run.model.configured", {"record": {"display_label": "muse-wonder-1.0"}}),
            rec("runtime.user_intent.accepted", {"semantic_kind": {"kind": "chat"}}),
            rec("tool_batch.effect.started",
                {"record": {"tool_name": "read_file", "effect_id": "e1", "call_id": "c1"}}),
            rec("tool_batch.effect.terminal",
                {"record": {"effect_id": "e1", "outcome": {"kind": "completed"}}}),
            rec("approval_wait.effect.started", {"record": {"tool_name": "bash"}}),
        ]
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")

    def tearDown(self):
        self.dir.cleanup()

    def test_once_frame_is_honest(self):
        out = subprocess.run([sys.executable, SCRIPT, "--session", self.log, "--once"],
                             capture_output=True, text=True, timeout=20).stdout
        text = plain(out)
        self.assertIn("WONDER", text)
        self.assertIn("Wonder · waiting for approval", text)
        self.assertIn("approval asked", text)
        # A terminal record with no tool_name still names the started tool,
        # and a return is never dressed up as a success verdict.
        self.assertIn("read_file closed (completed)", text)
        self.assertNotIn("succeeded", text)
        # Prompt text is never shown; only its receipt is.
        self.assertIn("prompt received", text)

    def test_live_follow_without_tty(self):
        proc = subprocess.Popen([sys.executable, SCRIPT, "--session", self.log],
                                stdout=subprocess.PIPE, text=True)
        try:
            time.sleep(1.2)
            with open(self.log, "a", encoding="utf-8") as f:
                f.write(rec("tool_batch.effect.started",
                            {"record": {"tool_name": "edit_file",
                                        "effect_id": "e2", "call_id": "c2"}}) + "\n")
            time.sleep(1.2)
        finally:
            proc.terminate()
            live = proc.communicate(timeout=10)[0]
        text = plain(live)
        self.assertIn("editing — edit_file", text)
        self.assertIn("Wonder · editing", text)


class NarrowPaneTest(unittest.TestCase):
    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_line_wraps_at_42_cells_and_tools_leave_one_note(self):
        margin = self.load_margin()
        m = margin.Margin()
        m.feed(json.loads(rec("tool_batch.effect.started",
                              {"record": {"tool_name": "read_file", "effect_id": "e1"}})))
        m.feed(json.loads(rec("tool_batch.effect.terminal",
                              {"record": {"effect_id": "e1", "outcome": {"kind": "completed"}}})))
        texts = [text for _, _, text in m.notes]
        self.assertNotIn("reading — read_file", texts)
        self.assertIn("read_file closed (completed)", texts)
        for line in plain(margin.render(m, 42, 44)).splitlines():
            self.assertLessEqual(len(line), 42, line)

    def test_read_head_names_logged_file_and_collapses_on_return(self):
        margin = self.load_margin()
        m = margin.Margin()
        m.feed(json.loads(rec("tool_batch.effect.started",
                              {"record": {"tool_name": "edit_file", "effect_id": "e9",
                                           "parallel_profile": {"subject": "workspace:wonder-margin/sidecar/margin.py"}}})))
        self.assertIn("editing — margin.py", [text for _, _, text in m.notes])
        self.assertEqual(m.sigil, "✎")
        m.feed(json.loads(rec("tool_batch.effect.terminal",
                              {"record": {"effect_id": "e9", "outcome": {"kind": "completed"}}})))
        texts = [text for _, _, text in m.notes]
        self.assertNotIn("editing — margin.py", texts)
        self.assertIn("margin.py marked (completed)", texts)

    def test_mark_row_names_deed_and_clock_ticks_while_working(self):
        margin = self.load_margin()
        m = margin.Margin()
        m.feed(json.loads(rec("tool_batch.effect.started",
                              {"record": {"tool_name": "read_file", "effect_id": "e1",
                                           "parallel_profile": {"subject": "workspace:a/margin.py"}}})))
        text = plain(margin.render(m, 42, 44))
        self.assertIn("reading — margin.py", text)
        self.assertRegex(text, r"Wonder · reading · \d+s")
        self.assertIn("┄", text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 42, line)

    def test_past_marks_cool_behind_the_head(self):
        import re as _re
        margin = self.load_margin()
        m = margin.Margin()
        m.feed(json.loads(rec("tool_batch.effect.started",
                              {"record": {"tool_name": "read_file", "effect_id": "e1"}})))
        m.feed(json.loads(rec("tool_batch.effect.started",
                              {"record": {"tool_name": "bash", "effect_id": "e2"}})))
        text = plain(margin.render(m, 42, 44))
        rows = [line for line in text.splitlines() if _re.match(r"\s*│[§~✎›?!·]", line)]
        self.assertGreaterEqual(len(rows), 2)
        self.assertNotEqual(rows[0], rows[-1])
        self.assertTrue(any("│§" in row for row in rows))
        for line in text.splitlines():
            self.assertLessEqual(len(line), 42, line)

    def test_approval_terminal_leaves_waiting_state_and_rhythm_fits(self):
        margin = self.load_margin()
        m = margin.Margin()
        m.feed(json.loads(rec("approval_wait.effect.started",
                              {"record": {"tool_name": "bash"}})))
        self.assertEqual(m.state, "waiting for approval")
        m.breathe = True
        m.feed(json.loads(rec("approval_wait.effect.terminal",
                              {"record": {"outcome": {"kind": "approved"}}})))
        self.assertEqual(m.state, "attending")
        text = plain(margin.render(m, 42, 44))
        self.assertIn("rhythm", text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 42, line)


class SecondSittingTest(unittest.TestCase):
    """2026-10-24 marks, each standing on a real host event shape."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fresh(self, mod):
        return mod.Margin(kept_path=os.path.join(tempfile.gettempdir(),
                                                  "wonder-no-such-kept.txt"))

    def feed(self, m, pt, payload, **kw):
        m.feed(json.loads(rec(pt, payload, **kw)))

    def test_branch_tool_and_subagent_events(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "subagent_spawn", "effect_id": "b1"}})
        self.assertEqual((m.sigil, m.state), ("⌥", "branching"))
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "b1", "outcome": {"kind": "completed"}}})
        # The spawn call returning only opens the branch; it is not the
        # branch back, and earns no tally stroke of its own.
        self.assertIn("branch call back (completed)", [t for _, _, t in m.notes])
        self.assertEqual(m.tally["branched"], 0)
        self.feed(m, "subagent.control.spawn_accepted", {"record": {}})
        self.feed(m, "subagent.control.result_ready", {"record": {}})
        self.assertIn("branch back — subagent result ready", [t for _, _, t in m.notes])
        self.assertEqual(m.tally["branched"], 1)  # one branch, counted once

    def test_workflow_child_edges_only(self):
        mod = self.load_margin(); m = self.fresh(mod)
        ev = lambda status: {"event": {"kind": "workflow_child_lifecycle",
                                       "status": status, "label": "reviewer"}}
        self.feed(m, "runtime.session", ev("started"))
        self.assertEqual(m.sigil, "⌥")
        marks = m.marks
        self.feed(m, "runtime.session", ev("usage"))
        self.assertEqual(m.marks, marks)  # bookkeeping is not a mark
        self.feed(m, "runtime.session", ev("completed"))
        self.assertIn("branch back — reviewer", [t for _, _, t in m.notes])

    def test_fold_only_when_installed(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "runtime.session",
                  {"event": {"kind": "context_compaction_candidate"}})
        self.assertEqual(m.marks, 0)  # a candidate is not a fold
        self.feed(m, "runtime.session",
                  {"event": {"kind": "context_compaction_installed"}})
        self.assertEqual(m.sigil, "¦")

    def test_nested_failure_and_cancel_are_not_laundered(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "edit_file", "effect_id": "e1"}})
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "e1", "outcome": {
                      "kind": "completed",
                      "task_completion": {"terminal": {"kind": "failed"}}}}})
        self.assertEqual(m.sigil, "!")
        self.assertIn("edit_file came back wrong: failed", [t for _, _, t in m.notes])
        self.assertEqual(m.tally["edited"], 0)  # failure earns no stroke
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "bash", "effect_id": "e2"}})
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "e2", "outcome": {
                      "kind": "completed",
                      "task_completion": {"terminal": {"kind": "cancelled"}}}}})
        self.assertEqual((m.sigil, m.state), ("—", "interrupted"))
        self.assertEqual(m.tally["ran"], 0)

    def test_session_end_and_real_timestamps(self):
        mod = self.load_margin(); m = self.fresh(mod)
        old = int((time.time() - 3600) * 1_000_000)
        self.feed(m, "runtime.user_intent.accepted", {}, recorded_at=old)
        self.assertLess(m.stamps[-1], time.time() - 3000)
        self.assertIn("last signal old", plain(mod.render(m, 42, 44)))
        self.feed(m, "session.end", {"record": {"exit_reason": "clean"}})
        self.assertEqual(m.state, "ended (clean)")

    def test_tally_counts_only_clean_returns_and_no_tick_ever(self):
        mod = self.load_margin(); m = self.fresh(mod)
        for tool, eid in (("read_file", "r1"), ("edit_file", "w1"), ("bash", "b1")):
            self.feed(m, "tool_batch.effect.started",
                      {"record": {"tool_name": tool, "effect_id": eid}})
            self.feed(m, "tool_batch.effect.terminal",
                      {"record": {"effect_id": eid, "outcome": {"kind": "completed"}}})
        text = plain(mod.render(m, 42, 44))
        self.assertIn("§ read 1", text)
        self.assertIn("✎ edited 1", text)
        self.assertIn("~ ran 1", text)
        self.assertNotIn("✓", text)  # the pane can prove returns, never passes

    def test_mcp_tool_name_shortened(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "mcp__cyclops_chat__room_read",
                              "effect_id": "m1"}})
        self.assertIn("working — room_read", [t for _, _, t in m.notes])
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "m1", "outcome": {"kind": "completed"}}})
        self.assertIn("room_read back (completed)", [t for _, _, t in m.notes])

    def test_kept_line_is_file_backed_or_absent(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            kept = os.path.join(d, "kept.txt")
            m = mod.Margin(kept_path=kept)
            self.feed(m, "runtime.user_intent.accepted", {})
            self.assertNotIn("a line kept", plain(mod.render(m, 42, 44)))
            with open(kept, "w", encoding="utf-8") as f:
                f.write("The margin is narrow on purpose.\n")
            text = plain(mod.render(m, 42, 44))
            self.assertIn("a line kept", text)
            self.assertIn("The margin is narrow on purpose.", text)
            compact = plain(mod.render(m, 42, 16))
            self.assertIn("kept ·", compact)
            for line in text.splitlines() + compact.splitlines():
                self.assertLessEqual(len(line), 42, line)

    def test_sideview_tip_box_latest_only_cleaned_or_absent(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            kept = os.path.join(d, "no-kept.txt")
            m = mod.Margin(kept_path=kept, sideview_path=tips, sideview_known_ids={"bbbb"}, sideview_installed=True)
            self.feed(m, "runtime.user_intent.accepted", {})
            # No tips log yet: no box, and nothing is invented.
            self.assertNotIn("from the side", plain(mod.render(m, 42, 44)))
            with open(tips, "w", encoding="utf-8") as f:
                f.write("# Cyclops Sideview — tips log\n\n"
                        "## 2026-10-25T00:00:00 · side session aaaa\n\n"
                        "Watched: the first look\n\n"
                        "◐ Sideview · the old tip nobody shows.\n\n"
                        "## 2026-10-25T01:00:00 · side session bbbb\n\n"
                        "Watched: the second look\n\n"
                        "◐ Sideview · check [muse-sideview](/x/muse-sideview:214) "
                        "for the `shell` case ✓\x1b[31m now.\n")
            text = plain(mod.render(m, 42, 44))
            self.assertIn("from the side", text)
            self.assertIn("check muse-sideview:214", text)
            self.assertIn("for the shell case", text)
            self.assertIn("the shell case", text)
            self.assertNotIn("the old tip nobody shows", text)
            # The side's text is data: cleaned on parse, no escape, no tick.
            parsed = mod.latest_sideview_tip(open(tips, encoding="utf-8").read())
            self.assertNotIn("\x1b", parsed)
            self.assertNotIn("✓", parsed)
            self.assertNotIn("✓", text)
            for line in text.splitlines():
                self.assertLessEqual(len(line), 42, line)
            # A visitor's comment is never a mark: no tally, no annotation.
            self.assertTrue(all(v == 0 for v in m.tally.values()))
            self.assertNotIn("check muse-sideview",
                             [t for _, _, t in m.notes])
            compact = plain(mod.render(m, 42, 16))
            self.assertIn("side ·", compact)
            for line in compact.splitlines():
                self.assertLessEqual(len(line), 42, line)

    def test_compact_top_form_keeps_status_line(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "read_file", "effect_id": "r1"}})
        text = plain(mod.render(m, 42, 16))
        lines = text.splitlines()
        self.assertLessEqual(len(lines), 16)
        self.assertIn("Wonder · reading", text)
        self.assertIn("talk in Muse pane", text)
        for line in lines:
            self.assertLessEqual(len(line), 42, line)


class CopyButtonTest(unittest.TestCase):
    """The copy button: copies Wonder's last committed message.

    The message text is held for copying, never rendered. Feedback lives
    on the button only — a click is a pane-local act, not a host mark.
    """

    SECRET = "LAST-ANSWER-TEXT-123"

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fresh(self, mod):
        return mod.Margin(kept_path=os.path.join(tempfile.gettempdir(),
                                                  "wonder-no-such-kept.txt"))

    def commit(self, m):
        m.feed(json.loads(rec("runtime.session", {"event": {
            "kind": "assistant_message_committed", "text": self.SECRET}})))

    def test_last_message_held_but_never_shown(self):
        mod = self.load_margin(); m = self.fresh(mod)
        text = plain(mod.render(m, 42, 44))
        self.assertIn("copy my last message · none yet", text)
        self.commit(m)
        self.assertEqual(m.last_answer, self.SECRET)
        text = plain(mod.render(m, 42, 44))
        self.assertIn("copy my last message", text)
        self.assertNotIn(self.SECRET, text)  # held for copying, never displayed
        for line in text.splitlines():
            self.assertLessEqual(len(line), 42, line)

    def test_input_parsing_click_key_quit(self):
        mod = self.load_margin()
        self.assertEqual(mod.parse_input("\x1b[<0;5;3M"), [("click", 5, 3)])
        self.assertEqual(mod.parse_input("\x1b[<0;5;3m"), [])   # release
        self.assertEqual(mod.parse_input("\x1b[<35;5;3M"), [])  # motion
        self.assertEqual(mod.parse_input("c"), [("copy",)])
        self.assertEqual(mod.parse_input("\x03"), [("quit",)])

    def test_button_hit_test_uses_rendered_geometry(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.commit(m)
        mod.render(m, 42, 44)
        row, col0, col1 = m.button
        self.assertTrue(mod.hit_button(m, col0 + 1, row + 1))
        self.assertFalse(mod.hit_button(m, col1 + 5, row + 1))
        self.assertFalse(mod.hit_button(m, col0 + 1, row + 3))

    def test_copy_feedback_is_honest_and_not_a_mark(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.commit(m)
        marks, notes = m.marks, list(m.notes)
        seen = []
        out = mod.do_copy(m, deliver=lambda t, emit: seen.append(t) or "copied",
                          emit=lambda s: None)
        self.assertEqual(out, "copied")
        self.assertEqual(seen, [self.SECRET])
        self.assertIn("copied", plain(mod.render(m, 42, 44)))
        out = mod.do_copy(m, deliver=lambda t, emit: "sent", emit=lambda s: None)
        self.assertEqual(out, "sent")
        # OSC52 was emitted, nothing verified: the button may only say so.
        self.assertIn("copy sent", plain(mod.render(m, 42, 44)))
        m.copy_until = 0
        self.assertIn("copy my last message", plain(mod.render(m, 42, 44)))
        self.assertEqual(m.marks, marks)
        self.assertEqual(m.notes, notes)

    def test_copy_with_nothing_committed(self):
        mod = self.load_margin(); m = self.fresh(mod)
        called = []
        out = mod.do_copy(m, deliver=lambda t, emit: called.append(t) or "copied",
                          emit=lambda s: None)
        self.assertEqual(out, "nothing")
        self.assertEqual(called, [])
        self.assertIn("nothing yet", plain(mod.render(m, 42, 44)))

    def test_compact_form_keeps_the_button(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.commit(m)
        text = plain(mod.render(m, 42, 16))
        self.assertIn("copy my last message", text)
        self.assertLessEqual(len(text.splitlines()), 16)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 42, line)


class ReviewFixTest(unittest.TestCase):
    """Regressions from the 2026-10-24 fresh-eyes review of this pane."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fresh(self, mod):
        return mod.Margin(kept_path=os.path.join(tempfile.gettempdir(),
                                                  "wonder-no-such-kept.txt"))

    def feed(self, m, pt, payload):
        m.feed(json.loads(rec(pt, payload)))

    def cycle(self, m, tool, eid, terminal_tool=True):
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": tool, "effect_id": eid, "call_id": eid + "c"}})
        term = {"effect_id": eid, "call_id": eid + "c", "outcome": {"kind": "completed"}}
        if terminal_tool:
            term["tool_name"] = tool
        self.feed(m, "tool_batch.effect.terminal", {"record": term})

    def test_arrows_paste_and_bursts_are_inert(self):
        mod = self.load_margin()
        self.assertEqual(mod.parse_input("\x1b[C"), [])        # Right arrow
        self.assertEqual(mod.parse_input("\x1b[1;5C"), [])     # Ctrl-Right
        self.assertEqual(mod.parse_input("code it, quickly"), [])
        self.assertEqual(mod.parse_input("\x1b[200~q\x1b[201~"), [])  # bracketed paste
        self.assertEqual(mod.parse_input("cq"), [])            # burst, not keys
        self.assertEqual(mod.parse_input("c"), [("copy",)])
        self.assertEqual(mod.parse_input("q"), [("quit",)])
        self.assertEqual(mod.parse_input("\x1b[<0;5;3M"), [("click", 5, 3)])

    def test_active_map_does_not_leak(self):
        mod = self.load_margin(); m = self.fresh(mod)
        for i in range(5):
            self.cycle(m, "bash", f"e{i}", terminal_tool=True)
        self.assertEqual((len(m.active), len(m.pending)), (0, 0))
        for i in range(5):
            self.cycle(m, "bash", f"f{i}", terminal_tool=False)
        self.assertEqual((len(m.active), len(m.pending)), (0, 0))

    def test_untrusted_text_cannot_inject_escapes_or_the_tick(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            kept = os.path.join(d, "kept.txt")
            with open(kept, "w", encoding="utf-8") as f:
                f.write("\x1b[31mINJECTED \x1b[32m✓\n")
            m = mod.Margin(kept_path=kept)
            frame = mod.render(m, 42, 44)
            self.assertNotIn("\x1b[31mINJECTED", frame)
            self.assertNotIn("✓", plain(frame))
            self.assertIn("INJECTED", plain(frame))  # words stay, control goes
        m2 = self.fresh(mod)
        self.feed(m2, "tool_batch.effect.started",
                  {"record": {"tool_name": "read_file", "effect_id": "x1",
                              "parallel_profile": {"subject": "workspace:\x1b[32m✓evil.py"}}})
        self.assertNotIn("✓", plain(mod.render(m2, 42, 44)))
        self.assertNotIn("\x1b[32m✓", "".join(t for _, _, t in m2.notes))

    def test_parallel_same_file_calls_are_two_deeds(self):
        mod = self.load_margin(); m = self.fresh(mod)
        subj = {"subject": "workspace:a/same.py"}
        for eid in ("p1", "p2"):
            self.feed(m, "tool_batch.effect.started",
                      {"record": {"tool_name": "read_file", "effect_id": eid,
                                  "parallel_profile": subj}})
        texts = [t for _, _, t in m.notes]
        self.assertEqual(texts.count("reading — same.py"), 1)  # one display mark
        self.assertEqual(m.marks, 2)                            # two deeds seen
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "p1", "outcome": {"kind": "completed"}}})
        self.assertIn("reading — same.py", [t for _, _, t in m.notes])  # sibling still runs
        self.assertEqual(m.tally["read"], 1)
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "p2", "outcome": {"kind": "completed"}}})
        self.assertNotIn("reading — same.py", [t for _, _, t in m.notes])
        self.assertEqual(m.tally["read"], 2)

    def test_orphan_terminal_invents_no_deed(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "ghost", "tool_name": "bash",
                              "outcome": {"kind": "completed"}}})
        self.assertIn("bash returned (completed)", [t for _, _, t in m.notes])
        self.assertEqual(m.tally["ran"], 0)
        self.assertEqual((len(m.active), len(m.pending)), (0, 0))

    def test_waited_counts_at_return_not_at_asking(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "approval_wait.effect.started", {"record": {"tool_name": "bash"}})
        self.assertEqual(m.tally["waited"], 0)
        self.feed(m, "approval_wait.effect.terminal",
                  {"record": {"outcome": {"kind": "approved"}}})
        self.assertEqual(m.tally["waited"], 1)

    def test_button_hitbox_matches_clipped_drawing(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "runtime.session", {"event": {
            "kind": "assistant_message_committed", "text": "held"}})
        mod.render(m, 30, 44)
        row, col0, col1 = m.button
        self.assertLessEqual(col1, 30)
        self.assertFalse(mod.hit_button(m, 35, row + 1))  # past the drawing
        self.assertTrue(mod.hit_button(m, col0 + 2, row + 1))

    def test_wide_characters_count_two_cells(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            kept = os.path.join(d, "kept.txt")
            with open(kept, "w", encoding="utf-8") as f:
                f.write("保持冷静并继续前进，保持冷静并继续前进\n")
            m = mod.Margin(kept_path=kept)
            for line in plain(mod.render(m, 42, 44)).splitlines():
                self.assertLessEqual(mod.display_width(line), 42, line)

    def test_adoption_never_steals_a_live_session(self):
        mod = self.load_margin()
        self.assertFalse(mod.should_adopt(False, 10, 1))     # both live
        self.assertTrue(mod.should_adopt(True, 10, 1))       # ours ended
        self.assertTrue(mod.should_adopt(False, 400, 1))     # ours long quiet
        self.assertFalse(mod.should_adopt(False, 400, 500))  # other quieter still

    def test_load_tail_returns_consumed_offset(self):
        mod = self.load_margin(); m = self.fresh(mod)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "session.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write(rec("session.started", {"kind": "session_started"}) + "\n")
            offset = mod.load_tail(m, path)
            self.assertEqual(offset, os.path.getsize(path))
            with open(path, "a", encoding="utf-8") as f:
                f.write("NEWLINE\n")
            with open(path, encoding="utf-8") as f:
                f.seek(offset)
                self.assertEqual(f.read(), "NEWLINE\n")  # nothing skipped


class SecondReviewTest(unittest.TestCase):
    """Regressions from the second fresh-eyes review (0.3.2)."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fresh(self, mod):
        return mod.Margin(kept_path=os.path.join(tempfile.gettempdir(),
                                                  "wonder-no-such-kept.txt"))

    def feed(self, m, pt, payload, **kw):
        m.feed(json.loads(rec(pt, payload, **kw)))

    def cycle(self, m, tool, eid, outcome="completed", nested=None):
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": tool, "effect_id": eid}})
        out = {"kind": outcome}
        if nested:
            out["task_completion"] = {"terminal": {"kind": nested}}
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": eid, "outcome": out}})

    def test_session_end_reason_is_sanitised(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "session.end", {"record": {"exit_reason": "\x1b[31mEVIL ✓ FAKE"}})
        frame = mod.render(m, 42, 44)
        self.assertNotIn("\x1b[31mEVIL", frame)
        self.assertNotIn("✓", plain(frame))
        self.assertNotIn("✓", m.state)
        self.assertEqual(mod.clean("a" + chr(0x202E) + "b" + chr(0x200B) + "c"), "abc")

    def test_model_is_dash_until_configured(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "runtime.user_intent.accepted", {})
        text = plain(mod.render(m, 42, 44))
        self.assertNotIn("muse-wonder-full-1.0", text)
        self.feed(m, "run.model.configured", {"record": {"display_label": "muse-x-9"}})
        self.assertIn("muse-x-9", plain(mod.render(m, 42, 44)))

    def test_tally_allowlist_and_nested_synonyms(self):
        mod = self.load_margin()
        for outcome in ("timeout", "aborted", "denied", "rejected", "something-new"):
            m = self.fresh(mod)
            self.cycle(m, "bash", "e1", outcome=outcome)
            self.assertEqual(m.tally["ran"], 0, outcome)
            self.assertIn(f"bash returned ({outcome})", [t for _, _, t in m.notes])
        for nested in ("failure", "error"):
            m = self.fresh(mod)
            self.cycle(m, "bash", "e1", nested=nested)
            self.assertEqual(m.sigil, "!", nested)
            self.assertEqual(m.tally["ran"], 0, nested)
        m = self.fresh(mod)
        self.cycle(m, "bash", "e1")
        self.assertEqual(m.tally["ran"], 1)  # completed still earns its stroke

    def test_return_moves_the_mark_off_the_deed(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.cycle(m, "read_file", "r1")
        self.assertEqual(m.state, "attending")
        self.assertNotIn("Wonder · reading", plain(mod.render(m, 42, 44)))

    def test_orphan_endings_earn_no_stroke(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "approval_wait.effect.terminal",
                  {"record": {"outcome": {"kind": "approved"}}})
        self.assertEqual(m.tally["waited"], 0)
        self.feed(m, "runtime.session", {"event": {
            "kind": "workflow_child_lifecycle", "status": "completed",
            "label": "ghost"}})
        self.assertEqual(m.tally["branched"], 0)
        self.feed(m, "subagent.control.result_ready", {"record": {}})
        self.assertEqual(m.tally["branched"], 0)

    def test_partial_lines_are_buffered_not_dropped(self):
        mod = self.load_margin(); m = self.fresh(mod)
        line = rec("tool_batch.effect.started",
                   {"record": {"tool_name": "read_file", "effect_id": "p1"}})
        carry = mod.feed_buffer(m, line[:20])
        self.assertEqual(carry, line[:20])
        self.assertEqual(m.marks, 0)
        carry = mod.feed_buffer(m, line[20:] + "\n", carry)
        self.assertEqual(carry, "")
        self.assertIn("reading — read_file", [t for _, _, t in m.notes])

    def test_emoji_family_and_combining_widths(self):
        mod = self.load_margin()
        fam = "\U0001F468" + chr(0x200D) + "\U0001F469" + chr(0x200D) + "\U0001F467"
        self.assertEqual(mod.display_width(fam), 2)
        self.assertEqual(mod.display_width("e" + chr(0x301)), 1)  # combining acute
        self.assertLessEqual(mod.display_width(mod.clip(fam * 30, 42)), 42)


class ThirdReviewTest(unittest.TestCase):
    """Regressions from the third fresh-eyes review (0.3.3)."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fresh(self, mod):
        return mod.Margin(kept_path=os.path.join(tempfile.gettempdir(),
                                                  "wonder-no-such-kept.txt"))

    def feed(self, m, pt, payload, **kw):
        m.feed(json.loads(rec(pt, payload, **kw)))

    def test_responding_matches_real_host_shape(self):
        # Real logs declare a model call as side_effect_intent with
        # operation=model.meta.response — never as scheduled/started
        # with that operation (0 matches across local session logs).
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "runtime.session", {"event": {
            "kind": "side_effect_intent", "operation": "model.meta.response"}})
        self.assertEqual(m.state, "responding")

    def test_parallel_same_label_workflow_children_each_count(self):
        mod = self.load_margin(); m = self.fresh(mod)
        ev = lambda status: {"event": {"kind": "workflow_child_lifecycle",
                                       "status": status, "label": "reviewer"}}
        for _ in range(3):
            self.feed(m, "runtime.session", ev("started"))
        for _ in range(3):
            self.feed(m, "runtime.session", ev("completed"))
        self.assertEqual(m.tally["branched"], 3)

    def test_us_spelling_canceled_is_an_interrupt(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "bash", "effect_id": "e1"}})
        self.feed(m, "tool_batch.effect.terminal",
                  {"record": {"effect_id": "e1", "outcome": {"kind": "canceled"}}})
        self.assertEqual((m.sigil, m.state), ("—", "interrupted"))
        self.assertEqual(m.tally["ran"], 0)

    def test_future_timestamp_never_shows_a_negative_clock(self):
        mod = self.load_margin(); m = self.fresh(mod)
        future = int((time.time() + 3600) * 1_000_000)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "bash", "effect_id": "e1"}},
                  recorded_at=future)
        self.assertNotIn("· -", plain(mod.render(m, 42, 44)))

    def test_render_never_exceeds_a_narrow_pane(self):
        mod = self.load_margin(); m = self.fresh(mod)
        self.feed(m, "tool_batch.effect.started",
                  {"record": {"tool_name": "read_file", "effect_id": "e1"}})
        for line in plain(mod.render(m, 20, 44)).splitlines():
            self.assertLessEqual(mod.display_width(line), 20, line)

    def test_malformed_records_do_not_raise(self):
        mod = self.load_margin(); m = self.fresh(mod)
        for bad in (
            {"payload_type": "session.started", "stream": {"id": 12345}, "payload": {}},
            {"payload_type": "approval_wait.effect.terminal",
             "payload": {"record": {"outcome": "approved"}}},
            {"payload_type": "runtime.session", "payload": {"event": {
                "kind": "workflow_child_lifecycle", "status": "started", "label": ["x"]}}},
            {"payload_type": "tool_batch.effect.started",
             "payload": {"record": {"tool_name": "bash", "effect_id": ["x"]}}},
            {"payload_type": "tool_batch.effect.terminal",
             "payload": {"record": {"effect_id": "e1", "outcome": "completed"}}},
        ):
            m.feed(bad)  # must not raise; the line is simply not evidence

    def test_live_pane_waits_for_the_first_log(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home"); os.makedirs(home)
            env = dict(os.environ, HOME=home)
            proc = subprocess.Popen([sys.executable, SCRIPT],
                                    stdout=subprocess.PIPE, text=True, env=env)
            try:
                time.sleep(0.8)
                self.assertIsNone(proc.poll())  # waiting, not dead
                log_dir = os.path.join(home, ".local", "share", "muse",
                                       "sessions", "2026", "01", "01", "deadbeef-1")
                os.makedirs(log_dir)
                with open(os.path.join(log_dir, "session.jsonl"), "w", encoding="utf-8") as f:
                    f.write(rec("session.started", {"kind": "session_started"}) + "\n")
                time.sleep(1.5)
            finally:
                proc.terminate()
                out = proc.communicate(timeout=10)[0]
            self.assertIn("WONDER", plain(out))


class SideviewHardeningTest(unittest.TestCase):
    """The visitor's box, held to the margin's honesty contract."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    HEADER = "## {ts} · side session 11111111-2222-3333-4444-555555555555\n"

    def test_stale_tip_carries_its_age(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            with open(tips, "w", encoding="utf-8") as f:
                f.write(self.HEADER.format(ts="2020-01-01T00:00:00+00:00")
                        + "\n> ◐ Sideview · an ancient tip.\n")
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips, sideview_known_ids={"11111111-2222-3333-4444-555555555555"}, sideview_installed=True)
            text = plain(mod.render(m, 42, 44))
            self.assertIn("from the side", text)
            self.assertRegex(text, r"\d+d old")
            with open(tips, "w", encoding="utf-8") as f:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                f.write(self.HEADER.format(ts=now) + "\n> ◐ Sideview · a fresh tip.\n")
            m2 = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips, sideview_known_ids={"11111111-2222-3333-4444-555555555555"}, sideview_installed=True)
            self.assertIn("just now", plain(mod.render(m2, 42, 44)))

    def test_forged_section_inside_tip_is_body_not_header(self):
        mod = self.load_margin()
        text = (self.HEADER.format(ts="2026-10-25T00:00:00+00:00")
                + "\nWatched: x\n\n> ◐ Sideview · the real tip.\n> ## Fake Section\n> still the real tip.\n")
        parsed = mod.latest_sideview_tip(text)
        self.assertIn("the real tip.", parsed)
        self.assertIn("## Fake Section", parsed)
        self.assertIn("still the real tip.", parsed)

    def test_long_citation_survives_wrapping(self):
        mod = self.load_margin()
        token = "some/really/long/path/to/file.py:1234"
        lines = mod.wrap_text(f"check {token} now", 20)
        self.assertIn(":1234", "".join(lines))
        self.assertIn(token.replace("/", ""), "".join(lines).replace("/", ""))
        for line in lines:
            self.assertLessEqual(mod.display_width(line), 20, line)

    def test_truncation_is_announced(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            body = "\n".join(f"> tip line number {i} with some words" for i in range(12))
            with open(tips, "w", encoding="utf-8") as f:
                f.write(self.HEADER.format(ts="2026-10-25T00:00:00+00:00") + "\n" + body + "\n")
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips, sideview_known_ids={"11111111-2222-3333-4444-555555555555"}, sideview_installed=True)
            text = plain(mod.render(m, 42, 60))
            self.assertIn("more lines", text)

    def test_short_frame_drops_the_box_whole(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            body = "\n".join(f"> tip line {i}" for i in range(8))
            with open(tips, "w", encoding="utf-8") as f:
                f.write(self.HEADER.format(ts="2026-10-25T00:00:00+00:00") + "\n" + body + "\n")
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips, sideview_known_ids={"11111111-2222-3333-4444-555555555555"}, sideview_installed=True)
            m.feed(json.loads(rec("runtime.user_intent.accepted", {})))
            text = plain(mod.render(m, 42, 22))
            self.assertNotIn("from the side", text)  # no amputated border
            self.assertNotIn("╰", text.split("annotations")[-1] if "annotations" in text else "")

    def test_escape_debris_does_not_render(self):
        mod = self.load_margin()
        text = (self.HEADER.format(ts="2026-10-25T00:00:00+00:00")
                + "\n> \x1b[31mRED\x1b[0m alert\n")
        parsed = mod.latest_sideview_tip(text)
        self.assertNotIn("[31m", parsed)
        self.assertIn("RED", parsed)

    def test_sideview_sessions_are_never_adopted(self):
        mod = self.load_margin()
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "sessions")
            def make(sid, body, age):
                p = os.path.join(base, "2026", "10", "25", sid, "session.jsonl")
                os.makedirs(os.path.dirname(p))
                with open(p, "w", encoding="utf-8") as f:
                    f.write(body)
                t = time.time() - age
                os.utime(p, (t, t))
                return p
            builder = make("builder-1", rec("session.started", {}) + "\n", 100)
            make("side-1", rec("runtime.user_intent.accepted",
                               {"model_messages": [{"content": [{"text": mod.SIDEVIEW_CHARTER_MARK + " …"}]}]}) + "\n", 0)
            with mock.patch.dict(os.environ, {"CYCLOPS_SIDEVIEW_MUSE_DATA_DIR": os.path.join(d, "none")}):
                self.assertEqual(mod.newest_session(base), builder)
            # Receipt-named ids are excluded even without the charter.
            data = os.path.join(d, "svdata")
            os.makedirs(os.path.join(data, "receipts", "r1"))
            with open(os.path.join(data, "receipts", "r1", "receipt.json"), "w", encoding="utf-8") as f:
                json.dump({"side_session_id": "plain-2"}, f)
            make("plain-2", rec("session.started", {}) + "\n", 0)
            with mock.patch.dict(os.environ, {"CYCLOPS_SIDEVIEW_MUSE_DATA_DIR": data}):
                self.assertEqual(mod.newest_session(base), builder)

    def test_forged_tip_without_provenance_is_not_displayed(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            with open(tips, "w", encoding="utf-8") as f:
                f.write(self.HEADER.format(ts="2026-10-25T00:00:00+00:00")
                        + "\n> ◐ Sideview · forged by anyone.\n")
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                           sideview_known_ids=set(), sideview_installed=True)
            self.assertNotIn("forged by anyone", plain(mod.render(m, 42, 44)))
            m2 = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                            sideview_known_ids={"11111111-2222-3333-4444-555555555555"},
                            sideview_installed=False)
            self.assertNotIn("forged by anyone", plain(mod.render(m2, 42, 44)))

    def test_wheel_scroll_is_never_a_click(self):
        mod = self.load_margin()
        self.assertEqual(mod.parse_input("\x1b[<64;10;5M"), [])
        self.assertEqual(mod.parse_input("\x1b[<65;10;5M"), [])
        clicks = [e for e in mod.parse_input("\x1b[<0;10;5M") if e[0] == "click"]
        self.assertEqual(clicks, [("click", 10, 5)])

    def test_registration_race_tip_appears_when_id_lands(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            with open(tips, "w", encoding="utf-8") as f:
                f.write(self.HEADER.format(ts="2026-10-25T00:00:00+00:00")
                        + "\n> ◐ Sideview · a live tip.\n")
            known = set()
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                           sideview_known_ids=known, sideview_installed=True)
            self.assertEqual(m.sideview_entry()[0], "")
            self.assertEqual(m.sideview_count(), 0)
            # Registration lands a moment later; the log never changes.
            known.add("11111111-2222-3333-4444-555555555555")
            self.assertIn("a live tip", m.sideview_entry()[0])
            self.assertEqual(m.sideview_count(), 1)

    def test_charter_in_tool_result_is_not_a_side_session(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "sessions")
            def make(sid, rows):
                p = os.path.join(base, "2026", "10", "25", sid, "session.jsonl")
                os.makedirs(os.path.dirname(p))
                with open(p, "w", encoding="utf-8") as f:
                    f.write("\n".join(rows) + "\n")
                return p
            charter = mod.SIDEVIEW_CHARTER_MARK
            builder = make("builder-9", [
                rec("runtime.user_intent.accepted", {"text": "build the thing"}),
                rec("tool_batch.effect.terminal",
                    {"record": {"outcome": {"kind": "completed"}}, "text": charter}),
            ])
            self.assertFalse(mod.is_sideview_session(builder, known_ids=set()))
            quoting = make("builder-10", [
                rec("runtime.user_intent.accepted",
                    {"text": f"please review this charter: {charter}"}),
            ])
            self.assertFalse(mod.is_sideview_session(quoting, known_ids=set()))
            side = make("side-9", [
                rec("session.started", {}),
                rec("runtime.user_intent.accepted",
                    {"model_messages": [{"content": [{"text": charter + " …"}]}]}),
            ])
            self.assertTrue(mod.is_sideview_session(side, known_ids=set()))

    def test_running_pane_re_resolves_tips_path(self):
        mod = self.load_margin()
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            d1 = os.path.join(d, "state1"); d2 = os.path.join(d, "state2")
            os.makedirs(d1); os.makedirs(d2)
            hdr = self.HEADER.format(ts="2026-10-25T00:00:00+00:00")
            with open(os.path.join(d2, "tips.md"), "w", encoding="utf-8") as f:
                f.write(hdr + "\n> ◐ Sideview · tip from the custom dir.\n")
            with open(os.path.join(d1, "tips.md"), "w", encoding="utf-8") as f:
                f.write(hdr + "\n> ◐ Sideview · tip from the default dir.\n")
            with open(os.path.join(d1, "active-data-dir.txt"), "w", encoding="utf-8") as f:
                f.write(d2 + "\n")
            env = {"CYCLOPS_SIDEVIEW_MUSE_DATA_DIR": d1}
            known = {"11111111-2222-3333-4444-555555555555"}
            with mock.patch.dict(os.environ, env):
                m = mod.Margin(kept_path=os.path.join(d, "no.txt"),
                               sideview_known_ids=known, sideview_installed=True)
                text, _ = m.sideview_entry()
                self.assertIn("custom dir", text)
                os.unlink(os.path.join(d1, "active-data-dir.txt"))
                text, _ = m.sideview_entry()
                self.assertIn("default dir", text)

    def test_oversized_entry_announces_instead_of_vanishing(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            with open(tips, "w", encoding="utf-8") as f:
                f.write(self.HEADER.format(ts="2026-10-25T00:00:00+00:00") + "\n> " + "x" * (300 * 1024) + "\n")
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                           sideview_known_ids={"11111111-2222-3333-4444-555555555555"},
                           sideview_installed=True)
            text, _ = m.sideview_entry()
            self.assertIn("larger than the margin reads", text)


class SideviewToggleTest(unittest.TestCase):
    """The margin's second button: turn the visitor on and off."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fake_runner(self, calls, pane_alive=True):
        class Proc:
            def __init__(self, rc=0, out=""):
                self.returncode, self.stdout = rc, out
        def run(argv, **kw):
            calls.append(argv)
            if "split-window" in argv:
                return Proc(0, "%99\n")
            if "display-message" in argv:
                return Proc(0 if pane_alive else 1, "%99\n" if pane_alive else "")
            return Proc(0, "")
        return run

    def test_toggle_opens_then_closes_a_pane(self):
        mod = self.load_margin()
        import unittest.mock as mock
        calls = []
        m = mod.Margin(kept_path="/nonexistent-kept.txt",
                       sideview_known_ids=set(), sideview_installed=True)
        m.cwd = "/work/project"
        fakebin_dir = tempfile.mkdtemp()
        fakebin = os.path.join(fakebin_dir, "muse-sideview")
        with open(fakebin, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
        os.chmod(fakebin, 0o755)
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/fake,1,0",
                                          "MARGIN_SIDEVIEW_BIN": fakebin}):
            self.assertEqual(mod.toggle_sideview(m, runner=self.fake_runner(calls)), "on")
            self.assertEqual(m.sideview_target, "%99")
            split = [c for c in calls if "split-window" in c]
            self.assertIn("/work/project", split[0])
            self.assertIn("muse-sideview", split[0][-1])
            self.assertNotIn("--watch", split[0][-1])  # the button opens the conversation
            self.assertIn("Watch this work from the side", split[0][-1])
            self.assertEqual(mod.toggle_sideview(m, runner=self.fake_runner(calls)), "off")
            self.assertIsNone(m.sideview_target)
            self.assertTrue(any("kill-pane" in c for c in calls))
        # A toggle is a pane-local act: no marks, no tally.
        self.assertEqual(m.marks, 0)
        self.assertTrue(all(v == 0 for v in m.tally.values()))

    def test_toggle_outside_tmux_uses_a_session(self):
        mod = self.load_margin()
        import unittest.mock as mock
        calls = []
        m = mod.Margin(kept_path="/nonexistent-kept.txt",
                       sideview_known_ids=set(), sideview_installed=True)
        fakebin_dir = tempfile.mkdtemp()
        fakebin = os.path.join(fakebin_dir, "muse-sideview")
        with open(fakebin, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
        os.chmod(fakebin, 0o755)
        env = dict(os.environ, MARGIN_SIDEVIEW_BIN=fakebin)
        env.pop("TMUX", None)
        # clear=True is what actually removes TMUX: patch.dict with
        # clear=False never deletes keys missing from the new dict, so
        # this test used to take the inside-tmux branch (and fail)
        # whenever the suite itself ran inside tmux.
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(mod.toggle_sideview(m, runner=self.fake_runner(calls)), "on")
            self.assertEqual(m.sideview_kind, "session")
            self.assertTrue(any("new-session" in c for c in calls))

    def test_toggle_without_sideview_installed_says_so(self):
        mod = self.load_margin()
        import unittest.mock as mock
        m = mod.Margin(kept_path="/nonexistent-kept.txt",
                       sideview_known_ids=set(), sideview_installed=True)
        with mock.patch.dict(os.environ, {"MARGIN_SIDEVIEW_BIN": "/no/such/bin",
                                          "HOME": "/nonexistent-home",
                                          "PATH": "/nonexistent"}):
            with mock.patch.object(mod.shutil, "which", return_value=None):
                self.assertEqual(mod.toggle_sideview(m, runner=self.fake_runner([])), "missing")
            self.assertIn("not found", m.side_feedback)

    def test_dead_pane_reopens_instead_of_lying_on(self):
        mod = self.load_margin()
        import unittest.mock as mock
        calls = []
        m = mod.Margin(kept_path="/nonexistent-kept.txt",
                       sideview_known_ids=set(), sideview_installed=True)
        m.sideview_target, m.sideview_kind = "%42", "pane"
        fakebin_dir = tempfile.mkdtemp()
        fakebin = os.path.join(fakebin_dir, "muse-sideview")
        with open(fakebin, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
        os.chmod(fakebin, 0o755)
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/fake,1,0",
                                          "MARGIN_SIDEVIEW_BIN": fakebin}):
            result = mod.toggle_sideview(m, runner=self.fake_runner(calls, pane_alive=False))
            self.assertEqual(result, "on")
            self.assertEqual(m.sideview_target, "%99")

    def test_button_renders_and_v_key_parses(self):
        mod = self.load_margin()
        m = mod.Margin(kept_path="/nonexistent-kept.txt",
                       sideview_known_ids=set(), sideview_installed=True)
        text = plain(mod.render(m, 42, 44))
        self.assertIn("Open Side Review Conversation", text)
        self.assertIsNotNone(m.side_button)
        row, col0, col1 = m.side_button
        self.assertTrue(mod.hit_side_button(m, col0 + 2, row + 1))
        m.sideview_target = "%1"
        self.assertIn("Side Review: open", plain(mod.render(m, 42, 44)))
        self.assertIn(("sideview",), mod.parse_input("v"))
        self.assertEqual(mod.parse_input("paste v text"), [])


class SideLogToggleTest(unittest.TestCase):
    """The third button: read every tip, not just the latest."""

    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    HEADER = "## 2026-10-25T0{i}:00:00+00:00 · side session sid-{i}\n"

    def make(self, mod, d, n=5):
        tips = os.path.join(d, "tips.md")
        with open(tips, "w", encoding="utf-8") as f:
            for i in range(n):
                f.write(self.HEADER.format(i=i) + f"\n> ◐ Sideview · tip number {i}.\n\n")
        m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                       sideview_known_ids={f"sid-{i}" for i in range(n)},
                       sideview_installed=True)
        return m, tips

    def fake_runner(self, calls):
        class Proc:
            def __init__(self, rc=0, out=""):
                self.returncode, self.stdout = rc, out
        def run(argv, **kw):
            calls.append(argv)
            if "split-window" in argv:
                return Proc(0, "%77\n")
            if "display-message" in argv:
                return Proc(0, "%77\n")
            return Proc(0, "")
        return run

    def test_count_and_box_still_latest_only(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            m, _ = self.make(mod, d, 5)
            self.assertEqual(m.sideview_count(), 5)
            text, _ = m.sideview_entry()
            self.assertIn("tip number 4", text)
            frame = plain(mod.render(m, 48, 60))
            self.assertIn("side log · 5", frame)
            self.assertNotIn("tip number 3", frame)

    def test_log_opens_pager_pane_then_closes(self):
        mod = self.load_margin()
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as d:
            m, tips = self.make(mod, d, 3)
            calls = []
            with mock.patch.dict(os.environ, {"TMUX": "/tmp/fake,1,0"}):
                self.assertEqual(mod.toggle_side_log(m, runner=self.fake_runner(calls)), "open")
                self.assertEqual(m.log_target, "%77")
                split = [c for c in calls if "split-window" in c][0]
                self.assertIn(tips, split[-1])
                self.assertEqual(mod.toggle_side_log(m, runner=self.fake_runner(calls)), "closed")
                self.assertIsNone(m.log_target)
                self.assertTrue(any("kill-pane" in c for c in calls))

    def test_log_with_no_tips_says_none_yet(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"),
                           sideview_path=os.path.join(d, "absent.md"),
                           sideview_known_ids=set(), sideview_installed=True)
            self.assertEqual(mod.toggle_side_log(m, runner=self.fake_runner([])), "empty")
            self.assertIn("none yet", m.log_feedback)
            self.assertIn("side log · none yet", plain(mod.render(m, 42, 44)))

    def test_log_button_geometry_and_l_key(self):
        mod = self.load_margin()
        with tempfile.TemporaryDirectory() as d:
            m, _ = self.make(mod, d, 2)
            plain(mod.render(m, 42, 44))
            self.assertIsNotNone(m.log_button)
            row, col0, col1 = m.log_button
            self.assertTrue(mod.hit_log_button(m, col0 + 2, row + 1))
            self.assertFalse(mod.hit_log_button(m, col0 + 2, row + 2))
            self.assertIn(("sidelog",), mod.parse_input("l"))


class SideviewIntegrationTest(unittest.TestCase):
    """The real Sideview launcher's output through the real Margin parser."""

    def test_launcher_tip_renders_in_margin(self):
        root = os.path.dirname(ROOT)
        launcher = os.path.join(ROOT, "muse-sideview")
        if not os.path.exists(launcher):
            self.skipTest("muse-sideview launcher not present")
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            fakebin = os.path.join(d, "bin"); os.makedirs(fakebin)
            fake = os.path.join(fakebin, "muse")
            with open(fake, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env python3\nimport json\n"
                        "print(json.dumps({'payload_type': 'run.output.delta', 'payload': {'text': '◐ Sideview · integration tip: mind the seam.'}}))\n")
            os.chmod(fake, 0o755)
            work = os.path.join(d, "work"); os.makedirs(work)
            state = os.path.join(d, "state")
            env = dict(os.environ, PATH=f"{fakebin}:{os.environ.get('PATH', '')}")
            env.pop("CYCLOPS_SIDEVIEW_SESSION", None)
            env["XDG_STATE_HOME"] = os.path.join(d, "xdg-state")
            proc = subprocess.run(
                [sys.executable, launcher, "--once", "--data-dir", state,
                 "--cwd", work, "watch the seam"],
                capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            found = sorted(Path(state).glob("projects/*/tips.md"))
            self.assertEqual(len(found), 1, found)
            tips = str(found[0])
            # Margin computes the identical per-project path from cwd.
            self.assertEqual(tips, mod.project_tips_path(state, work))
            with open(tips, encoding="utf-8") as f:
                entry = mod.latest_sideview_entry(f.read())
            self.assertIn("integration tip", entry["text"])
            self.assertTrue(entry["session"])
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                           sideview_known_ids={entry["session"]},
                           sideview_installed=True)
            frame = plain(mod.render(m, 48, 60))
            self.assertIn("from the side · Sideview ·", frame)
            self.assertIn("integration tip", frame)


class SideviewOverrideAndCountTests(unittest.TestCase):
    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _write(self, path, sess, text, when):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"\n## {when.isoformat()} · side session {sess}\n"
                    "Watched: x\n" + "".join("> " + line + "\n" for line in text.splitlines()) + "\n")

    def test_env_override_wins_over_per_project_resolution(self):
        import datetime
        import unittest.mock as mock
        mod = self.load_margin()
        now = datetime.datetime.now(datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "state")
            cwd = os.path.join(d, "proj"); os.makedirs(cwd)
            explicit = os.path.join(d, "my-explicit-tips.md")
            self._write(explicit, "side-a", "explicit tip", now)
            self._write(mod.project_tips_path(state, cwd), "side-a", "project tip", now)
            env = {"CYCLOPS_SIDEVIEW_MUSE_DATA_DIR": state,
                   "MARGIN_SIDEVIEW_TIPS": explicit}
            with mock.patch.dict(os.environ, env):
                m = mod.Margin(kept_path=os.path.join(d, "no.txt"),
                               sideview_known_ids={"side-a"},
                               sideview_installed=True)
                m.cwd = cwd
                self.assertEqual(m.sideview_entry()[0], "explicit tip")

    def test_side_log_count_covers_the_whole_log(self):
        import datetime
        mod = self.load_margin()
        now = datetime.datetime.now(datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            tips = os.path.join(d, "tips.md")
            with open(tips, "w", encoding="utf-8") as f:
                for i in range(300):
                    f.write(f"\n## {now.isoformat()} · side session side-a\n"
                            "Watched: x\n> " + ("tip %d " % i) + ("x" * 1000) + "\n")
            self.assertGreater(os.path.getsize(tips), mod.SIDEVIEW_TAIL_BYTES)
            m = mod.Margin(kept_path=os.path.join(d, "no.txt"), sideview_path=tips,
                           sideview_known_ids={"side-a"}, sideview_installed=True)
            self.assertEqual(m.sideview_count(), 300)


class MarginPerProjectTests(unittest.TestCase):
    def load_margin(self):
        spec = importlib.util.spec_from_file_location("margin", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _write(self, path, sess, text, when):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"\n## {when.isoformat()} · side session {sess}\n"
                    "Watched: x\n" + "".join("> " + line + "\n" for line in text.splitlines()) + "\n")

    def test_margin_shows_only_its_own_project_and_legacy_fallback(self):
        import datetime
        import unittest.mock as mock
        mod = self.load_margin()
        now = datetime.datetime.now(datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "state")
            cwd_a, cwd_b = os.path.join(d, "a"), os.path.join(d, "b")
            for c in (cwd_a, cwd_b):
                os.makedirs(c)
            self._write(mod.project_tips_path(state, cwd_a), "side-a", "tip for A", now)
            self._write(mod.project_tips_path(state, cwd_b), "side-b", "tip for B", now)
            self._write(os.path.join(state, "tips.md"), "side-a", "legacy global", now)
            with mock.patch.dict(os.environ, {"CYCLOPS_SIDEVIEW_MUSE_DATA_DIR": state}):
                m = mod.Margin(kept_path=os.path.join(d, "no.txt"),
                               sideview_known_ids={"side-a", "side-b"},
                               sideview_installed=True)
                m.cwd = cwd_a
                self.assertEqual(m.sideview_entry()[0], "tip for A")
                self.assertNotIn("tip for B", plain(mod.render(m, 48, 60)))
                # A project with no log of its own shows nothing —
                # never another project's stale global word. The
                # legacy log appears only before the cwd is known.
                cwd_c = os.path.join(d, "c"); os.makedirs(cwd_c)
                m.cwd = cwd_c
                self.assertEqual(m.sideview_entry()[0], "")
                self.assertEqual(m.sideview_count(), 0)
                m.cwd = ""
                self.assertEqual(m.sideview_entry()[0], "legacy global")
                # Once that project gets its own log, it takes over.
                m.cwd = cwd_c
                self._write(mod.project_tips_path(state, cwd_c), "side-a", "tip for C", now)
                self.assertEqual(m.sideview_entry()[0], "tip for C")


if __name__ == "__main__":
    unittest.main()
