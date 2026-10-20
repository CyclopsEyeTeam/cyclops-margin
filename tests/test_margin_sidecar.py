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


def rec(pt, payload):
    return json.dumps({"payload_type": pt, "payload": payload,
                       "stream": {"id": "deadbeef-1234"}})


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


if __name__ == "__main__":
    unittest.main()
