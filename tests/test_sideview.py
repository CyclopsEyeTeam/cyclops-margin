#!/usr/bin/env python3
"""Tests for muse-sideview with fake muse/tmux binaries. No model requests."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "muse-sideview"
TIP = "◐ Sideview · fake tip: check the edge case."

FAKE_MUSE = """#!/usr/bin/env python3
import json, os, sys
rec = os.environ.get("FAKE_RECORD")
_prompt = ""
if "--prompt-file" in sys.argv:
    try:
        _prompt = open(sys.argv[sys.argv.index("--prompt-file") + 1], encoding="utf-8").read()
    except OSError:
        _prompt = ""
if rec:
    with open(rec, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": sys.argv[1:], "prompt": _prompt,
                             "marker": os.environ.get("CYCLOPS_SIDEVIEW_SESSION")}) + "\\n")
print(json.dumps({"payload_type": "run.output.delta", "payload": {"text": "◐ Sideview · fake tip: "}}))
print(json.dumps({"payload_type": "run.output.delta", "payload": {"text": "check the edge case."}}))
"""

FAKE_TMUX = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_TMUX_RECORD"
"""


def load_module(name, path):
    import importlib.util
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SideviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.work = base / "work"
        self.work.mkdir()
        (self.work / "note.md").write_text("# notes\n", encoding="utf-8")
        self.state = base / "state"
        self.bindir = base / "bin"
        self.bindir.mkdir()
        self.record = base / "muse-record.jsonl"
        self.tmux_record = base / "tmux-record.txt"
        muse = self.bindir / "muse"
        muse.write_text(FAKE_MUSE, encoding="utf-8")
        muse.chmod(0o755)
        tmux = self.bindir / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_sideview(self, *args, extra_env=None, stdin=""):
        env = dict(os.environ)
        env["PATH"] = f"{self.bindir}:{env.get('PATH', '')}"
        env["FAKE_RECORD"] = str(self.record)
        env["FAKE_TMUX_RECORD"] = str(self.tmux_record)
        env["XDG_STATE_HOME"] = str(Path(self.tmp.name) / "xdg-state")
        env["CYCLOPS_SIDEVIEW_TMUX_CAPTURE_SECS"] = "0"
        env.pop("TMUX", None)
        env.pop("CYCLOPS_SIDEVIEW_SESSION", None)
        env.pop("MUSE_SESSION_ID", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(LAUNCHER), "--data-dir", str(self.state),
             "--cwd", str(self.work), *args],
            capture_output=True, text=True, env=env, input=stdin, timeout=30)

    def project_tips(self):
        found = sorted(self.state.glob("projects/*/tips.md"))
        self.assertEqual(len(found), 1, found)
        return found[0]

    def receipts(self):
        return sorted((self.state / "receipts").glob("*"))

    def last_receipt(self):
        dirs = self.receipts()
        self.assertTrue(dirs, "expected a receipt directory")
        return dirs[-1]

    def test_once_happy_path(self):
        proc = self.run_sideview("--once", "watch the notes")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(TIP, proc.stdout)
        tips = self.project_tips().read_text(encoding="utf-8")
        self.assertIn(TIP, tips)
        self.assertIn("Watched: watch the notes", tips)
        receipt = self.last_receipt()
        payload = json.loads((receipt / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["mode"], "once")
        self.assertEqual(payload["topic_first80"], "watch the notes")
        self.assertTrue(payload["side_session_id"])
        record0 = json.loads(self.record.read_text(encoding="utf-8").splitlines()[-1])
        self.assertIn("passive side view", record0["prompt"])
        self.assertIn("watch the notes", record0["prompt"])
        self.assertFalse((receipt / "prompt.txt").exists())
        self.assertEqual(stat.S_IMODE((receipt / "receipt.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o700)
        record = json.loads(self.record.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["marker"], "1")
        argv = record["argv"]
        self.assertIn("--disable-write", argv)
        self.assertIn("--disable-shell", argv)
        self.assertIn("--disable-web-tools", argv)
        self.assertIn("--prompt-file", argv)

    def test_tips_are_per_project(self):
        other = Path(self.tmp.name) / "other-project"
        other.mkdir()
        self.run_sideview("--once", "tip run one")
        self.run_sideview("--once", "--cwd", str(other), "tip run two")
        project_dirs = sorted((self.state / "projects").iterdir())
        self.assertEqual(len(project_dirs), 2)
        joined = " ".join((p / "tips.md").read_text(encoding="utf-8") for p in project_dirs)
        self.assertIn("fake tip: check the edge case", joined)
        markers = " ".join((p / "project.txt").read_text(encoding="utf-8") for p in project_dirs)
        self.assertIn(str(self.work.resolve()), markers)
        self.assertIn(str(other.resolve()), markers)
        self.assertFalse((self.state / "tips.md").exists())

    def test_once_allow_shell_lifts_shell_disable(self):
        proc = self.run_sideview("--once", "--allow-shell", "watch")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        argv = json.loads(self.record.read_text(encoding="utf-8").splitlines()[-1])["argv"]
        self.assertIn("--disable-write", argv)
        self.assertNotIn("--disable-shell", argv)

    def test_prepare_only_stores_no_prompt(self):
        proc = self.run_sideview("--once", "--prepare-only", "a secret-ish topic")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<prompt-file>", proc.stdout)
        receipt = self.last_receipt()
        self.assertFalse((receipt / "prompt.txt").exists())
        payload = json.loads((receipt / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "prepared")
        self.assertNotIn("a secret-ish topic", json.dumps(payload))
        self.assertFalse(self.record.exists(), "fake muse must not be launched")

    def test_nested_launch_refused(self):
        proc = self.run_sideview("--once", "watch",
                                 extra_env={"CYCLOPS_SIDEVIEW_SESSION": "1"})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("refusing to nest", proc.stderr)
        self.assertFalse(self.record.exists())

    def test_builder_session_id_never_in_prompt(self):
        proc = self.run_sideview("--once", "watch",
                                 extra_env={"MUSE_SESSION_ID": "builder-secret-123"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        receipt = self.last_receipt()
        # The prompt file is deleted once the child finishes: only its
        # hash stays, so neither the builder id nor the exact words
        # linger in the receipt.
        self.assertFalse((receipt / "prompt.txt").exists())
        for name in ("receipt.json", "result.txt"):
            self.assertNotIn("builder-secret-123",
                             (receipt / name).read_text(encoding="utf-8"))

    def test_evidence_outside_cwd_refused(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("hi\n", encoding="utf-8")
        proc = self.run_sideview("--once", "--evidence", str(outside), "watch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("outside --cwd", proc.stderr)

    def test_evidence_credential_name_refused(self):
        (self.work / ".env").write_text("X=1\n", encoding="utf-8")
        proc = self.run_sideview("--once", "--evidence", ".env", "watch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("credential", proc.stderr)

    def test_evidence_long_form_secret_name_refused(self):
        (self.work / "creds.json").write_text(
            '{"aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}\n',
            encoding="utf-8")
        proc = self.run_sideview("--once", "--evidence", "creds.json", "watch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("secret", proc.stderr)

    def test_evidence_named_in_prompt(self):
        proc = self.run_sideview("--once", "--evidence", "note.md", "watch")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        prompt = json.loads(self.record.read_text(encoding="utf-8").splitlines()[-1])["prompt"]
        self.assertIn(str(self.work / "note.md"), prompt)

    def test_tmux_split_inside_tmux(self):
        proc = self.run_sideview("--tmux", "watch the refactor",
                                 extra_env={"TMUX": "/tmp/fake,1,0"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("its own pane", proc.stdout)
        recorded = self.tmux_record.read_text(encoding="utf-8")
        self.assertIn("split-window", recorded)
        self.assertIn("muse", recorded)
        self.assertIn("CYCLOPS_SIDEVIEW_SESSION=1", recorded)
        # The prompt is pasted via a buffer, never embedded in argv:
        # the topic and charter must not appear in any tmux command.
        self.assertNotIn("watch the refactor", recorded)
        self.assertNotIn("passive side view", recorded)
        self.assertIn("load-buffer", recorded)
        self.assertIn("paste-buffer", recorded)

    def test_dash_leading_topic_after_double_dash(self):
        proc = self.run_sideview("--once", "--", "-watch the dash case")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        prompt = json.loads(self.record.read_text(encoding="utf-8").splitlines()[-1])["prompt"]
        self.assertIn("-watch the dash case", prompt)

    def test_registry_and_completion_stamp(self):
        proc = self.run_sideview("--once", "watch the notes")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads((self.last_receipt() / "receipt.json").read_text(encoding="utf-8"))
        self.assertIn("completed", payload)
        registry = (Path(self.tmp.name) / "xdg-state" / "cyclops-sideview-muse"
                    / "side-sessions.jsonl").read_text(encoding="utf-8")
        self.assertIn(payload["side_session_id"], registry)
        tips = self.project_tips().read_text(encoding="utf-8")
        header = [ln for ln in tips.splitlines() if ln.startswith("## ")][-1]
        self.assertGreaterEqual(header[3:].split(" ·")[0], payload["created"])
        pointer = (Path(self.tmp.name) / "xdg-state" / "cyclops-sideview-muse"
                   / "active-data-dir.txt").read_text(encoding="utf-8")
        self.assertIn(str(self.state), pointer)

    def test_negative_timeout_is_a_clean_refusal(self):
        proc = self.run_sideview("--once", "--timeout=-1", "watch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--timeout", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_once_tmux_conflict_is_a_clean_refusal(self):
        proc = self.run_sideview("--once", "--tmux", "watch")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("contradict", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_allow_write_alone_keeps_shell_and_web_off(self):
        proc = self.run_sideview("--once", "--allow-write", "watch")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        argv = json.loads(self.record.read_text(encoding="utf-8").splitlines()[-1])["argv"]
        self.assertNotIn("--disable-write", argv)
        self.assertIn("--disable-shell", argv)
        self.assertIn("--disable-web-tools", argv)

    def test_events_file_is_0600_and_data_dir_hint_shows(self):
        proc = self.run_sideview("--once", "watch")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        events = self.last_receipt() / "native.events.jsonl"
        self.assertEqual(stat.S_IMODE(events.stat().st_mode), 0o600)
        self.assertIn("MARGIN_SIDEVIEW_TIPS", proc.stderr)

    def test_tmux_captures_real_session_id(self):
        sessions = Path(self.tmp.name) / "sessions"
        logdir = sessions / "2026" / "10" / "25" / "realside-123"
        tmux = self.bindir / "tmux"
        tmux.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_TMUX_RECORD\"\n"
            f"mkdir -p {logdir}\n"
            f"touch {logdir}/session.jsonl\n", encoding="utf-8")
        tmux.chmod(0o755)
        proc = self.run_sideview(
            "--tmux", "watch",
            extra_env={"CYCLOPS_SIDEVIEW_TMUX_CAPTURE_SECS": "5",
                       "CYCLOPS_SIDEVIEW_MUSE_SESSIONS": str(sessions)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads((self.last_receipt() / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["side_session_id"], "realside-123")
        registry = (Path(self.tmp.name) / "xdg-state" / "cyclops-sideview-muse"
                    / "side-sessions.jsonl").read_text(encoding="utf-8")
        self.assertIn("realside-123", registry)

    def test_interactive_instant_nonzero_exit_writes_no_opened_note(self):
        mod = load_module("muse_sideview", LAUNCHER)
        import unittest.mock as mock
        args = type("A", (), {"muse_bin": "muse", "topic_text": "watch",
                              "model": None, "allow_write": False,
                              "allow_shell": False})()
        import io
        tty = type("T", (io.StringIO,), {"isatty": lambda self: True})()
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td) / "state"
            with mock.patch.object(mod.sys, "stdin", tty), \
                 mock.patch.object(mod.sys, "stdout", tty), \
                 mock.patch.object(mod.subprocess, "call", return_value=1), \
                 mock.patch.object(mod, "session_ids_snapshot", return_value=set()):
                code = mod.run_interactive(args, "prompt", Path(td), data_dir)
            self.assertEqual(code, 1)
            tips = list(data_dir.glob("projects/*/tips.md"))
            self.assertEqual(tips, [])

    def test_password_is_prose_in_evidence_is_refused(self):
        secret = self.work / "prose.md"
        secret.write_text("the password is " + "hunter2" + "hunter2", encoding="utf-8")
        proc = self.run_sideview("--once", "--evidence", "prose.md", "check")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("secret", (proc.stderr + proc.stdout).lower())

    def test_tmux_new_session_outside_tmux(self):
        proc = self.run_sideview("--tmux", "watch the refactor")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        recorded = self.tmux_record.read_text(encoding="utf-8")
        self.assertIn("new-session", recorded)
        self.assertIn("sideview-", recorded)
        payload = json.loads((self.last_receipt() / "receipt.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["tmux_session"].startswith("sideview-"))
        tips = self.project_tips().read_text(encoding="utf-8")
        self.assertIn("live side session opened", tips)


class TipsLogAndFlagTests(unittest.TestCase):
    def load_launcher(self):
        return load_module("muse_sideview", LAUNCHER)

    def test_concurrent_appends_all_survive(self):
        mod = self.load_launcher()
        import threading
        with tempfile.TemporaryDirectory() as td:
            tips = Path(td) / "tips.md"
            def add(i):
                mod.append_tip(tips, "2026-10-25T00:00:00+00:00",
                               f"sid-{i}", "topic", f"tip number {i}")
            threads = [threading.Thread(target=add, args=(i,)) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            text = tips.read_text(encoding="utf-8")
            for i in range(8):
                self.assertIn(f"tip number {i}", text)
            self.assertEqual(text.count("## 2026-10-25"), 8)

    def test_model_cannot_forge_a_section(self):
        mod = self.load_launcher()
        with tempfile.TemporaryDirectory() as td:
            tips = Path(td) / "tips.md"
            mod.append_tip(tips, "2026-10-25T00:00:00+00:00", "sid-1",
                           "line one\n## Forged Topic", "real tip\n## Fake Section\nmore")
            text = tips.read_text(encoding="utf-8")
            self.assertIn("> ## Fake Section", text)
            self.assertIn("Watched: line one ## Forged Topic", text)
            self.assertEqual(text.count("\n## 2026-"), 1)

    def test_sync_pointer_writes_and_clears(self):
        mod = self.load_launcher()
        import os as _os
        with tempfile.TemporaryDirectory() as td:
            old = _os.environ.get("XDG_STATE_HOME")
            _os.environ["XDG_STATE_HOME"] = td
            try:
                default_dir = Path(td) / "cyclops-sideview-muse"
                pointer = default_dir / "active-data-dir.txt"
                mod.sync_pointer(Path(td) / "custom")
                self.assertTrue(pointer.exists())
                mod.sync_pointer(default_dir)
                self.assertFalse(pointer.exists())
            finally:
                if old is None:
                    _os.environ.pop("XDG_STATE_HOME", None)
                else:
                    _os.environ["XDG_STATE_HOME"] = old

    def test_pointer_resets_when_back_at_default(self):
        mod = self.load_launcher()
        import os as _os
        with tempfile.TemporaryDirectory() as td:
            old = _os.environ.get("XDG_STATE_HOME")
            _os.environ["XDG_STATE_HOME"] = td
            try:
                default_dir = Path(td) / "cyclops-sideview-muse"
                mod.register_side_session("sid-a", Path(td) / "custom")
                self.assertTrue((default_dir / "active-data-dir.txt").exists())
                mod.register_side_session("sid-b", default_dir)
                self.assertFalse((default_dir / "active-data-dir.txt").exists())
            finally:
                if old is None:
                    _os.environ.pop("XDG_STATE_HOME", None)
                else:
                    _os.environ["XDG_STATE_HOME"] = old

    def test_registry_pointer_is_absolute_for_relative_data_dir(self):
        mod = self.load_launcher()
        import os as _os
        with tempfile.TemporaryDirectory() as td:
            old = _os.environ.get("XDG_STATE_HOME")
            _os.environ["XDG_STATE_HOME"] = td
            try:
                mod.register_side_session("sid-rel", Path("relstate"))
            finally:
                if old is None:
                    _os.environ.pop("XDG_STATE_HOME", None)
                else:
                    _os.environ["XDG_STATE_HOME"] = old
            pointer = (Path(td) / "cyclops-sideview-muse"
                       / "active-data-dir.txt").read_text(encoding="utf-8").strip()
            self.assertTrue(Path(pointer).is_absolute(), pointer)
            self.assertTrue(pointer.endswith("relstate"), pointer)

    def test_truncated_extraction_is_flagged(self):
        mod = self.load_launcher()
        with tempfile.TemporaryDirectory() as td:
            events = Path(td) / "events.jsonl"
            line = json.dumps({"payload_type": "run.output.delta",
                               "payload": {"text": "x" * 100}}) + "\n"
            events.write_text(line * 10, encoding="utf-8")
            old = mod.MAX_EVENTS_BYTES
            mod.MAX_EVENTS_BYTES = 250
            try:
                text, truncated = mod._extract_result(events)
            finally:
                mod.MAX_EVENTS_BYTES = old
            self.assertTrue(truncated)
            self.assertLess(len(text), 1000)


class WatcherTests(unittest.TestCase):
    def load_launcher(self):
        return load_module("muse_sideview", LAUNCHER)

    def test_turn_end_with_edits_fires_after_debounce(self):
        mod = self.load_launcher()
        w = mod.Watcher(min_interval=180, cap=6, debounce=20)
        # Real host shape: tool name lives on the started record and
        # is linked to the terminal by effect_id; no paths in the log.
        w.feed({"payload_type": "tool_batch.effect.started",
                "payload": {"record": {"tool_name": "edit_file",
                                       "effect_id": "e1",
                                       "parallel_profile": {"subject": "workspace:src/a.py"}}}}, now=99.0)
        w.feed({"payload_type": "tool_batch.effect.terminal",
                "payload": {"record": {"effect_id": "e1",
                                       "outcome": {"kind": "completed"}}}}, now=100.0)
        # The real turn-end shape: runtime.session + event.kind.
        w.feed({"payload_type": "runtime.session",
                "payload": {"kind": "run", "event": {"kind": "assistant_message_committed"}}}, now=101.0)
        self.assertFalse(w.due(110.0))   # still in the quiet window
        self.assertTrue(w.due(122.0))
        topic, paths = w.consume(122.0)
        self.assertIn("Passive side look", topic)
        self.assertEqual(paths, ["src/a.py"])
        self.assertFalse(w.has_signal())

    def test_failure_alone_fires_and_cap_holds(self):
        mod = self.load_launcher()
        w = mod.Watcher(min_interval=0, cap=2, debounce=5)
        for i in range(2):
            w.failure = True
            w.last_event_at = 100.0 + i * 100
            self.assertTrue(w.due(106.0 + i * 100))
            w.consume(106.0 + i * 100)
        w.failure = True
        w.last_event_at = 400.0
        self.assertFalse(w.due(406.0))  # hourly cap reached

    def test_turn_end_without_edits_is_still(self):
        mod = self.load_launcher()
        w = mod.Watcher(min_interval=0, cap=6, debounce=1)
        w.feed({"payload_type": "runtime.session",
                "payload": {"kind": "run", "event": {"kind": "assistant_message_committed"}}}, now=50.0)
        self.assertFalse(w.due(100.0))

    def test_watch_conflicts_and_bad_spacing_refuse_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env.pop("CYCLOPS_SIDEVIEW_SESSION", None)
            for argv in (["--watch", "--once"], ["--watch", "--watch-cap=0"],
                         ["--watch", "a topic"], ["--watch", "--prepare-only"],
                         ["--watch", "--evidence", "x.py"]):
                proc = subprocess.run(
                    [sys.executable, str(LAUNCHER), *argv],
                    capture_output=True, text=True, env=env, timeout=30,
                    cwd=td)
                self.assertEqual(proc.returncode, 1, argv)
                self.assertNotIn("Traceback", proc.stderr)

    def test_failed_edit_is_a_failure_not_an_edit(self):
        mod = self.load_launcher()
        w = mod.Watcher(min_interval=0, cap=6, debounce=1)
        w.feed({"payload_type": "tool_batch.effect.started",
                "payload": {"record": {"tool_name": "edit_file", "effect_id": "e1",
                                       "parallel_profile": {"subject": "workspace:src/a.py"}}}}, now=99.0)
        w.feed({"payload_type": "tool_batch.effect.terminal",
                "payload": {"record": {"effect_id": "e1",
                                       "outcome": {"kind": "failed"}}}}, now=100.0)
        self.assertTrue(w.failure)
        self.assertEqual(w.edits, 0)
        self.assertEqual(w.edited_paths, [])

    def test_substring_tool_is_not_an_edit_and_started_entry_is_consumed(self):
        mod = self.load_launcher()
        w = mod.Watcher(min_interval=0, cap=6, debounce=1)
        w.feed({"payload_type": "tool_batch.effect.started",
                "payload": {"record": {"tool_name": "edit_file", "effect_id": "e1",
                                       "parallel_profile": {"subject": "workspace:src/a.py"}}}}, now=99.0)
        # Terminal carries its own (non-edit) tool name: the started
        # entry must still be consumed, not leaked.
        w.feed({"payload_type": "tool_batch.effect.terminal",
                "payload": {"record": {"effect_id": "e1", "tool_name": "credit_check",
                                       "outcome": {"kind": "completed"}}}}, now=100.0)
        self.assertEqual(w.edits, 0)
        self.assertEqual(w._started, {})
        # And a terminal whose tool name merely contains "edit" is not an edit.
        w.feed({"payload_type": "tool_batch.effect.terminal",
                "payload": {"record": {"tool_name": "credit_check",
                                       "outcome": {"kind": "completed"}}}}, now=101.0)
        self.assertEqual(w.edits, 0)


class MarginContractTests(unittest.TestCase):
    """Pin the shared contract from this side too (Margin pins it from hers)."""

    def test_contract_constants_match_margin(self):
        # Same plugin since the merge: margin.py is a sibling file in
        # this checkout, so this check must never skip.
        margin_py = ROOT / "sidecar" / "margin.py"
        self.assertTrue(margin_py.exists(), margin_py)
        sv = load_module("muse_sideview", LAUNCHER)
        mg = load_module("margin", margin_py)
        # The charter Margin greps for is the charter Sideview sends.
        self.assertIn(mg.SIDEVIEW_CHARTER_MARK, sv.CHARTER)
        # Margin's header regex parses what Sideview's writer emits,
        # and both honour the same env names.
        with tempfile.TemporaryDirectory() as td:
            tips = Path(td) / "tips.md"
            sv.append_tip(tips, "2026-10-25T00:00:00+00:00", "sid-contract",
                          "watch", "◐ Sideview · contract tip.")
            entry = mg.latest_sideview_entry(tips.read_text(encoding="utf-8"))
            self.assertEqual(entry["session"], "sid-contract")
            self.assertIn("contract tip", entry["text"])
        for name in ("CYCLOPS_SIDEVIEW_MUSE_DATA_DIR", "MARGIN_SIDEVIEW_TIPS"):
            self.assertIn(name, LAUNCHER.read_text(encoding="utf-8") if name.startswith("CYCLOPS") else margin_py.read_text(encoding="utf-8"))
        # The per-project tips path scheme is identical on both sides.
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td) / "proj"
            cwd.mkdir()
            self.assertEqual(str(sv.project_tips_path(td, cwd)),
                             mg.project_tips_path(td, str(cwd)))


class ExtractorAndCommandTests(unittest.TestCase):
    """Regression tests from the first live side view (real event envelope)."""

    def load_launcher(self):
        return load_module("muse_sideview", LAUNCHER)

    def test_extract_result_real_envelope(self):
        mod = self.load_launcher()
        with tempfile.TemporaryDirectory() as td:
            events = Path(td) / "events.jsonl"
            events.write_text(
                json.dumps({"payload_type": "run.output.delta",
                            "payload": {"text": "◐ Sideview · real "}}) + "\n"
                + json.dumps({"payload_type": "run.output.delta",
                              "payload": {"text": "envelope tip."}}) + "\n"
                + json.dumps({"payload_type": "tool.result",
                              "payload": {"text": "not output"}}) + "\n",
                encoding="utf-8")
            self.assertEqual(mod.extract_result(events),
                             "◐ Sideview · real envelope tip.")

    def test_interactive_command_is_read_only_like_headless(self):
        mod = self.load_launcher()
        import types
        args = types.SimpleNamespace(muse_bin="muse", model=None,
                                     allow_write=False, allow_shell=False)
        cmd = mod.interactive_command(args, "watch")
        self.assertIn("--disable-write", cmd)
        self.assertIn("--disable-shell", cmd)
        # No --disable-web-tools here on purpose: interactive `muse`
        # rejects that flag (verified against the real binary — it
        # prints usage and exits), so live panes keep web tools and
        # the README says so. Headless runs do deny them.
        self.assertNotIn("--disable-web-tools", cmd)
        args.allow_shell = True
        cmd = mod.interactive_command(args, "watch")
        self.assertIn("--disable-write", cmd)
        self.assertNotIn("--disable-shell", cmd)


if __name__ == "__main__":
    unittest.main()
