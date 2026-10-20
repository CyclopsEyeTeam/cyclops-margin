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
    return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=20, **kw)


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
            cmd = f"MUSE_BIN={stub} {LAUNCHER} side"
            r = tmux("new-session", "-d", "-s", SESSION, "-x", "160", "-y", "48", cmd)
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
                if "WONDER" in seen:
                    break
                time.sleep(0.25)
            self.assertIn("WONDER", seen)
            self.assertIn("in the margin", seen)
            main = tmux("capture-pane", "-p", "-t", f"{SESSION}:0.0").stdout
            self.assertIn("STUB-MUSE-RUNNING", main)


if __name__ == "__main__":
    unittest.main()
