"""Focused tests for margin-keep, the kept-line CLI.

Run: python3 -m unittest discover -s tests -v
A line is kept on purpose, in one plain file, or not at all.
"""
import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = os.path.join(ROOT, "margin-keep")


class MarginKeepTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "kept.txt")
        self.env = dict(os.environ, MARGIN_KEPT=self.path)

    def tearDown(self):
        self.dir.cleanup()

    def run_keep(self, *args):
        r = subprocess.run([KEEP, *args], capture_output=True, text=True,
                           env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_round_trip(self):
        self.assertIn("nothing kept", self.run_keep())
        self.assertIn("narrow on purpose",
                      self.run_keep("The margin is narrow on purpose."))
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "The margin is narrow on purpose.\n")
        self.assertIn("narrow on purpose", self.run_keep())
        # Keeping again replaces: a margin keeps one line, not a journal.
        self.run_keep("Second line.")
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "Second line.\n")
        self.run_keep("--clear")
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("nothing kept", self.run_keep())

    def test_newlines_flatten_and_blank_is_refused(self):
        out = self.run_keep("line1\nline2")
        self.assertIn("line1 line2", out)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "line1 line2\n")
        r = subprocess.run([KEEP, "   "], capture_output=True, text=True,
                           env=self.env, timeout=20)
        self.assertNotEqual(r.returncode, 0)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "line1 line2\n")  # refusal kept the old line

    def raw(self, *args, path=None):
        env = dict(self.env, MARGIN_KEPT=path or self.path)
        return subprocess.run([KEEP, *args], capture_output=True, text=True,
                              env=env, timeout=20)

    def test_failed_write_never_claims_kept(self):
        # A directory where the file belongs: the write cannot land.
        r = self.raw("a line", path=self.dir.name)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("kept ·", r.stdout)
        r = self.raw("--clear", path=self.dir.name)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("let go", r.stdout)

    def test_cr_bidi_and_the_tick_are_not_stored_or_shown(self):
        r = self.raw("a\rb" + chr(0x202E) + "c " + chr(0x2713))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.path, "rb") as f:
            data = f.read()
        self.assertNotIn(b"\r", data)
        self.assertNotIn(chr(0x202E).encode(), data)
        self.assertNotIn(chr(0x2713).encode(), data)
        r = self.raw()
        self.assertNotIn("\r", r.stdout)
        self.assertNotIn(chr(0x202E), r.stdout)
        self.assertNotIn(chr(0x2713), r.stdout)

    def test_symlink_at_kept_path_is_replaced_not_followed(self):
        victim = os.path.join(self.dir.name, "victim.txt")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("IMPORTANT\n")
        link = os.path.join(self.dir.name, "kept-link.txt")
        os.symlink(victim, link)
        r = self.raw("a kept line", path=link)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim, encoding="utf-8") as f:
            self.assertEqual(f.read(), "IMPORTANT\n")  # never truncated
        self.assertFalse(os.path.islink(link))
        with open(link, encoding="utf-8") as f:
            self.assertEqual(f.read(), "a kept line\n")

    def test_escapes_are_not_stored_or_shown(self):
        r = self.raw("red \x1b[31m alert")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("\x1b", r.stdout)
        with open(self.path, "rb") as f:
            self.assertNotIn(b"\x1b", f.read())
        r = self.raw()
        self.assertNotIn("\x1b", r.stdout)


if __name__ == "__main__":
    unittest.main()
