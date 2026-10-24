"""Focused tests for muse-margin argument handling.

Run: python3 -m unittest discover -s tests -v
Non-interactive calls must pass straight through to the real muse with
every layout spelling stripped — `--margin side` once leaked a bare
`side` into the forwarded arguments.
"""
import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "muse-margin")
SHIM = os.path.join(ROOT, "shim", "muse")


class LauncherArgsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.dir.name, "calls.log")
        self.stub = os.path.join(self.dir.name, "muse")
        with open(self.stub, "w", encoding="utf-8") as f:
            f.write('#!/bin/sh\necho "$@" >> "$FAKE_LOG"\n')
        os.chmod(self.stub, 0o755)
        self.env = dict(os.environ, MUSE_BIN=self.stub, FAKE_LOG=self.log)

    def tearDown(self):
        self.dir.cleanup()

    def forward(self, *args, launcher=None):
        with open(self.log, "w", encoding="utf-8"):
            pass
        r = subprocess.run([launcher or LAUNCHER, *args], input="x\n",
                           capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.log, encoding="utf-8") as f:
            return f.read().strip()

    def test_layout_spellings_are_stripped(self):
        for form in (["--margin", "side"], ["--margin=side"], ["--margin", "top"],
                     ["--margin"], ["side"], ["--top"], ["--side"]):
            self.assertEqual(self.forward(*form, "exec", "hi there"),
                             "exec hi there", form)

    def test_plain_args_untouched(self):
        self.assertEqual(self.forward("exec", "side quest"), "exec side quest")

    def test_margin_after_first_real_arg_is_muses(self):
        # Layout stripping is leading-position only: a `--margin` meant
        # for Muse itself must reach it byte-for-byte.
        self.assertEqual(self.forward("exec", "--margin", "side", "hi"),
                         "exec --margin side hi")
        self.assertEqual(self.forward("exec", "--margin=side"),
                         "exec --margin=side")
        self.assertEqual(self.forward("exec", "top"), "exec top")

    def test_help_is_the_launchers(self):
        r = subprocess.run([LAUNCHER, "--help"], capture_output=True,
                           text=True, env=self.env, timeout=20)
        self.assertIn("muse-margin", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_shim_never_execs_itself_via_sloppy_path(self):
        # The shim lives behind a symlink in bindir; a trailing-slash PATH
        # entry for bindir must still be recognised as the shim's own
        # directory, or find_real_muse returns the shim and it loops.
        bindir = os.path.join(self.dir.name, "shimbin")
        os.makedirs(bindir)
        os.symlink(SHIM, os.path.join(bindir, "muse"))
        env = dict(self.env)
        env["PATH"] = bindir + "/" + os.pathsep + self.dir.name + os.pathsep + "/usr/bin" + os.pathsep + "/bin"
        with open(self.log, "w", encoding="utf-8"):
            pass
        r = subprocess.run([os.path.join(bindir, "muse"), "hello", "world"],
                           input="x\n", capture_output=True, text=True,
                           env=env, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.log, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "hello world")

    def test_shim_forwards_and_intercepts(self):
        # PATH puts the stub `muse` first; the shim must find it as the
        # real binary, forward plain calls unchanged, and intercept
        # --margin (which then reaches the same stub via muse-margin).
        env = dict(self.env)
        env["PATH"] = self.dir.name + os.pathsep + "/usr/bin" + os.pathsep + "/bin"
        for args, expected in ((["hello", "world"], "hello world"),
                               (["exec", "--margin", "hi"], "exec --margin hi"),
                               (["--margin", "side", "exec", "hi"], "exec hi")):
            with open(self.log, "w", encoding="utf-8"):
                pass
            r = subprocess.run([SHIM, *args], input="x\n", capture_output=True,
                               text=True, env=env, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(self.log, encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), expected, args)


if __name__ == "__main__":
    unittest.main()
