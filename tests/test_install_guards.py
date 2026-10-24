"""Install/uninstall must never clobber a same-named file that is not
Wonder's, and must only remove links that point at this checkout.

Run: python3 -m unittest discover -s tests -v
Uses a stub `muse` (exit 0) so no real plugin operations happen.
"""
import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, "install.sh")
UNINSTALL = os.path.join(ROOT, "uninstall.sh")


class InstallGuardTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = self.dir.name
        self.home = os.path.join(base, "home")
        self.bin = os.path.join(base, "bin")
        os.makedirs(self.home)
        os.makedirs(self.bin)
        stub = os.path.join(self.bin, "muse")
        with open(stub, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(stub, 0o755)
        self.env = dict(os.environ, HOME=self.home, XDG_BIN_HOME=self.bin,
                        PATH=self.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin")
        self.env.pop("TMUX", None)

    def tearDown(self):
        self.dir.cleanup()

    def run_script(self, script, *args, cwd=None):
        return subprocess.run(["bash", script, *args], capture_output=True,
                              text=True, env=self.env, timeout=60, cwd=cwd)

    def test_install_refuses_to_clobber_a_strangers_file(self):
        victim = os.path.join(self.bin, "muse-margin")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("mine, not yours\n")
        r = self.run_script(INSTALL)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(victim, encoding="utf-8") as f:
            self.assertEqual(f.read(), "mine, not yours\n")

    def test_help_and_unknown_args_install_nothing(self):
        r = self.run_script(INSTALL, "--help")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("install.sh", r.stdout)
        self.assertFalse(os.path.lexists(os.path.join(self.bin, "muse-margin")))
        r = self.run_script(INSTALL, "--with-muse-shm")  # a typo, not silently ok
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.lexists(os.path.join(self.bin, "muse-margin")))
        r = self.run_script(UNINSTALL, "--help")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.run_script(UNINSTALL, "--bogus")
        self.assertNotEqual(r.returncode, 0)

    def test_same_basename_stranger_symlink_is_not_clobbered(self):
        other = os.path.join(self.dir.name, "other-tools")
        os.makedirs(other)
        target = os.path.join(other, "muse-margin")
        with open(target, "w", encoding="utf-8") as f:
            f.write("someone else's tool\n")
        link = os.path.join(self.bin, "muse-margin")
        os.symlink(target, link)
        r = self.run_script(INSTALL)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(link), target)
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "someone else's tool\n")

    def test_relative_stranger_symlink_judged_from_its_own_directory(self):
        stranger = os.path.join(self.dir.name, "stranger")
        os.makedirs(stranger)
        target = os.path.join(stranger, "margin-keep")
        with open(target, "w", encoding="utf-8") as f:
            f.write("not yours\n")
        link = os.path.join(self.bin, "margin-keep")
        os.symlink(os.path.join("..", "stranger", "margin-keep"), link)
        elsewhere = os.path.join(self.dir.name, "elsewhere")
        os.makedirs(elsewhere)
        r = self.run_script(INSTALL, cwd=elsewhere)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(link), os.path.join("..", "stranger", "margin-keep"))

    def test_manifest_that_only_mentions_the_name_is_not_ours(self):
        # A directory whose plugin.json merely mentions "wonder-margin"
        # (here in the description of a differently-named plugin) is
        # not a Wonder checkout: a same-named link into it is a
        # stranger's and must block the install, not be replaced.
        other = os.path.join(self.dir.name, "other-plugin")
        os.makedirs(os.path.join(other, ".muse-plugin"))
        with open(os.path.join(other, ".muse-plugin", "plugin.json"), "w", encoding="utf-8") as f:
            f.write('{"name": "someone-else", "description": "wonder-margin fan"}')
        target = os.path.join(other, "muse-margin")
        with open(target, "w", encoding="utf-8") as f:
            f.write("someone else's tool\n")
        link = os.path.join(self.bin, "muse-margin")
        os.symlink(target, link)
        r = self.run_script(INSTALL)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(link), target)

    def test_relative_link_to_this_checkout_still_refreshes(self):
        link = os.path.join(self.bin, "muse-margin")
        os.symlink(os.path.relpath(os.path.join(ROOT, "muse-margin"), self.bin), link)
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.readlink(link), os.path.join(ROOT, "muse-margin"))
        self.assertEqual(os.readlink(os.path.join(self.bin, "margin-pane")),
                         os.path.join(ROOT, "margin-pane"))

    def test_stranger_at_last_link_blocks_whole_install(self):
        # Pre-flight: a stranger's margin-keep (the LAST link) must stop
        # the install before ANY link or plugin change happens.
        victim = os.path.join(self.bin, "margin-keep")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("mine\n")
        r = self.run_script(INSTALL)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(os.path.join(self.bin, "muse-margin")))
        self.assertFalse(os.path.lexists(os.path.join(self.bin, "margin-pane")))

    def test_uninstall_removes_relative_links_into_checkout(self):
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        link = os.path.join(self.bin, "margin-pane")
        os.unlink(link)
        os.symlink(os.path.relpath(os.path.join(ROOT, "margin-pane"), self.bin), link)
        r = self.run_script(UNINSTALL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(link))

    def test_plugin_manifest_matches_changelog(self):
        import json, re
        with open(os.path.join(ROOT, ".muse-plugin", "plugin.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["name"], "wonder-margin")
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            latest = re.search(r"## (\d+\.\d+\.\d+)", f.read()).group(1)
        self.assertEqual(manifest["version"], latest)

    def test_install_uninstall_round_trip_and_stranger_kept(self):
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        link = os.path.join(self.bin, "muse-margin")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), os.path.join(ROOT, "muse-margin"))
        # Re-install over our own links refreshes cleanly.
        r = self.run_script(INSTALL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # A stranger's file at one name survives uninstall; ours goes.
        keep = os.path.join(self.bin, "margin-keep")
        os.unlink(keep)
        with open(keep, "w", encoding="utf-8") as f:
            f.write("mine\n")
        r = self.run_script(UNINSTALL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(link))
        with open(keep, encoding="utf-8") as f:
            self.assertEqual(f.read(), "mine\n")


class MarginPaneLinkTest(unittest.TestCase):
    def test_margin_pane_works_through_a_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "session.jsonl")
            with open(log, "w", encoding="utf-8") as f:
                f.write('{"payload_type": "session.started", "payload": {},'
                        ' "stream": {"id": "deadbeef-1234"}}\n')
            link = os.path.join(d, "margin-pane")
            os.symlink(os.path.join(ROOT, "margin-pane"), link)
            r = subprocess.run([link, "--session", log, "--once"],
                               capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("WONDER", r.stdout)


if __name__ == "__main__":
    unittest.main()
