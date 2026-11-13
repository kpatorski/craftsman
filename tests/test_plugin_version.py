"""Tests for plugin_version.py: which version of the plugin last touched the installed content, compared with the
running one -- see MANAGEMENT.md, "Plugin version". Comparing two files is a lookup, so a script does it, and the
marker is written by the script, never by the agent's Write tool, which may not write under Claude's own folder
without asking.

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import plugin_version  # noqa: E402


class PluginVersionTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.content = self.root / "craftsman"
        self.content.mkdir()
        self.marker = self.content / ".craftsman-plugin-version"

    def check(self, running="0.30.0"):
        return plugin_version.check(self.content, running)

    def test_an_older_marker_is_said_once_and_moved_to_the_running_version(self):
        self.marker.write_text("0.9.0\n")
        said = self.check()
        self.assertIn("0.9.0 → 0.30.0", said)
        self.assertIn("CHANGELOG.md", said)
        self.assertEqual(self.marker.read_text(), "0.30.0\n")
        self.assertIsNone(self.check(), "the second time there is nothing to say")

    def test_a_missing_marker_reads_as_unknown_and_is_written(self):
        self.assertIn("unknown → 0.30.0", self.check())
        self.assertEqual(self.marker.read_text(), "0.30.0\n")

    def test_a_newer_marker_is_said_and_kept(self):
        self.marker.write_text("0.31.0\n")
        said = self.check()
        self.assertIn("0.31.0", said)
        self.assertIn("fresh session", said)
        self.assertEqual(self.marker.read_text(), "0.31.0\n")

    def test_without_installed_content_nothing_is_said_or_written(self):
        shutil.rmtree(self.content)
        self.assertIsNone(self.check())
        self.assertFalse(self.content.exists())

    def test_the_running_version_is_the_plugins_own(self):
        manifest = SCRIPTS.parent / ".claude-plugin" / "plugin.json"
        self.assertEqual(plugin_version.running(), json.loads(manifest.read_text())["version"])

    def test_the_command_line_prints_what_to_say_or_nothing(self):
        def run():
            return subprocess.run([sys.executable, str(SCRIPTS / "plugin_version.py"), str(self.content)],
                                  capture_output=True, text=True, timeout=30)
        first, second = run(), run()
        self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr)
        self.assertIn("unknown →", first.stdout)
        self.assertEqual(second.stdout, "")


if __name__ == "__main__":
    unittest.main()
