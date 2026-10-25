"""Focused test for the muse-margin tmux launcher.

Run: python3 -m unittest discover -s tests -v
Skips honestly when tmux is unavailable. Uses a stub `muse` so no real
model runs: the launcher must split the window, put Wonder in the side
pane at the requested width, and leave the stub running in the main pane.
"""
import os, shutil, subprocess, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "muse-margin")
SESSION = "muse-margin-test"


TEST_TMPDIR = tempfile.mkdtemp(prefix="muse-margin-tmux-")
os.environ["TMUX_TMPDIR"] = TEST_TMPDIR  # isolated server; never the user's


def tmux(*args, **kw):
    # Never touch the ambient server: inside a tmux client $TMUX overrides
    # $TMUX_TMPDIR, so without this `kill-server` in tearDown would take
    # down the very terminal the tests were launched from. Every command
    # here targets the isolated server in TEST_TMPDIR only.
    env = dict(kw.pop("env", None) or os.environ)
    env.pop("TMUX", None)
    env.pop("TMUX_PANE", None)
    return subprocess.run(["tmux", *args], capture_output=True, text=True,
                          timeout=20, env=env, **kw)


@unittest.skipUnless(shutil.which("tmux"), "tmux unavailable")
class TmuxLauncherTest(unittest.TestCase):
    def tearDown(self):
        tmux("kill-session", "-t", SESSION)
        tmux("kill-server")

    def test_side_pane_opens_beside_stub_muse(self):
        tmux("kill-session", "-t", SESSION)
        with tempfile.TemporaryDirectory() as d:
            stub = os.path.join(d, "muse")
            with open(stub, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\necho STUB-MUSE-RUNNING\nsleep 60\n")
            os.chmod(stub, 0o755)
            # A hermetic session log for the pane to follow. Without one
            # the sidecar exits at once ("no session log yet") and the
            # split pane dies — which is what a clean CI HOME exposed:
            # this test used to pass only by borrowing the developer's
            # real ~/.local/share/muse/sessions.
            fake_home = os.path.join(d, "home")
            log_dir = os.path.join(fake_home, ".local", "share", "muse",
                                   "sessions", "2026", "01", "01", "deadbeef-1234")
            os.makedirs(log_dir)
            with open(os.path.join(log_dir, "session.jsonl"), "w", encoding="utf-8") as f:
                f.write('{"payload_type": "session.started", "payload": {},'
                        ' "stream": {"id": "deadbeef-1234"}}\n')
            cmd = f"HOME={fake_home} MUSE_BIN={stub} {LAUNCHER} side"
            # -e puts HOME in the session environment: the split margin
            # pane inherits that, not the main pane shell's variables.
            r = tmux("new-session", "-d", "-s", SESSION, "-x", "160", "-y", "48",
                     "-e", f"HOME={fake_home}", cmd)
            self.assertEqual(r.returncode, 0, r.stderr)

            panes = ""
            for _ in range(40):
                panes = tmux("list-panes", "-t", SESSION, "-F",
                             "#{pane_index} #{pane_width}").stdout.strip()
                if len(panes.splitlines()) == 2:
                    break
                time.sleep(0.25)
            lines = panes.splitlines()
            self.assertEqual(len(lines), 2, panes)
            side_width = int(lines[1].split()[1])
            self.assertTrue(40 <= side_width <= 44, panes)

            seen = ""
            for _ in range(40):
                seen = tmux("capture-pane", "-p", "-t", f"{SESSION}:0.1").stdout
                if "WONDER" in seen and "deadbeef" in seen:
                    break
                time.sleep(0.25)
            self.assertIn("WONDER", seen)
            self.assertIn("in the margin", seen)
            # The fake session's own id, not just any header: a pane
            # that borrowed a real ~/.local/share/muse session would
            # show WONDER too, and pass on a developer machine while
            # failing in CI. That is exactly what a clean CI HOME
            # exposed in the Case 2 test below.
            self.assertIn("deadbeef", seen)
            main = tmux("capture-pane", "-p", "-t", f"{SESSION}:0.0").stdout
            self.assertIn("STUB-MUSE-RUNNING", main)


    def test_dedicated_session_reaches_attach_with_margin(self):
        """Case 2 regression: a detached-created session must survive
        until attach (destroy-unattached used to kill it instantly,
        yielding 'margin pane could not open' + 'no sessions')."""
        tmux("kill-session", "-t", "muse-margin-outer")
        with tempfile.TemporaryDirectory() as d:
            stub = os.path.join(d, "muse")
            with open(stub, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\necho STUB-MUSE-RUNNING\nsleep 60\n")
            os.chmod(stub, 0o755)
            fake_home = os.path.join(d, "home")
            log_dir = os.path.join(fake_home, ".local", "share", "muse",
                                   "sessions", "2026", "01", "01", "deadbeef-5678")
            os.makedirs(log_dir)
            with open(os.path.join(log_dir, "session.jsonl"), "w", encoding="utf-8") as f:
                f.write('{"payload_type": "session.started", "payload": {},'
                        ' "stream": {"id": "deadbeef-5678"}}\n')
            # An outer pane gives the launcher a terminal; TMUX is
            # stripped inside the command so it takes the dedicated path.
            cmd = (f"env -u TMUX HOME={fake_home} MUSE_BIN={stub} {LAUNCHER}")
            r = tmux("new-session", "-d", "-s", "muse-margin-outer",
                     "-x", "160", "-y", "48", "-e", f"HOME={fake_home}", cmd)
            self.assertEqual(r.returncode, 0, r.stderr)
            dedicated = ""
            for _ in range(60):
                sessions = tmux("list-sessions", "-F", "#{session_name}").stdout.splitlines()
                found = [s for s in sessions
                         if s.startswith("muse-margin-") and s != "muse-margin-outer"]
                if found:
                    panes = tmux("list-panes", "-t", found[0]).stdout.strip()
                    if len(panes.splitlines()) == 2:
                        dedicated = found[0]
                        break
                time.sleep(0.25)
            self.assertTrue(dedicated, f"no dedicated session with 2 panes: {sessions}")
            seen = ""
            for _ in range(40):
                seen = tmux("capture-pane", "-p", "-t", f"{dedicated}:0.1").stdout
                if "WONDER" in seen and "deadbeef" in seen:
                    break
                time.sleep(0.25)
            self.assertIn("WONDER", seen)
            # The dedicated session is created detached, so without
            # the launcher's explicit HOME forwarding (ENV_FWD in
            # muse-margin) its panes would inherit the tmux server's
            # HOME: on a developer machine the pane then found real
            # session logs there and this test passed on borrowed
            # logs, while CI's clean HOME left it waiting forever.
            # Asserting the fake session id keeps the pass honest
            # on both machines.
            self.assertIn("deadbeef", seen)
            tmux("kill-session", "-t", dedicated)


if __name__ == "__main__":
    unittest.main()
