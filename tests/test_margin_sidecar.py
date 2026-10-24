"""Focused tests for the Wonder margin sidecar.

Run: python3 -m unittest discover -s tests -v
Covers: one-frame rendering from a session log, honest tool returns,
no prompt text shown, waiting-on-approval state, and live following
when stdout is not a TTY (the pane must not crash for lack of a
terminal size).
"""
import importlib.util, json, os, re, subprocess, sys, tempfile, time, unittest

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


if __name__ == "__main__":
    unittest.main()
