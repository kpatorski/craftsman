"""Tests for changed_since.py: what changed in a project since a craftsman session file was last written -- the
question a resumed run must answer before trusting what it read last time.

Run: python3 -m unittest discover -s tests
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts" / "changed_since.py"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class ChangedSinceTest(unittest.TestCase):
    def setUp(self):
        self.project = pathlib.Path(tempfile.mkdtemp())
        self.session = self.project / ".claude" / "sessions" / "implement-session-x.md"
        self.session.parent.mkdir(parents=True)
        self.session.write_text("# session\n")
        self.at(self.session, -100)

    def tearDown(self):
        shutil.rmtree(self.project)

    def at(self, path, seconds_from_now):
        stamp = time.time() + seconds_from_now
        os.utime(path, (stamp, stamp))

    def write(self, name, seconds_from_now, text="x"):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.at(path, seconds_from_now)
        return path

    def init_git(self):
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "dev@example.com")
        git(self.project, "config", "user.name", "dev")
        (self.project / ".gitignore").write_text(".claude/\nbuild/\n")
        self.at(self.project / ".gitignore", -200)

    def commit(self, message, when):
        git(self.project, "add", "-A")
        env = dict(os.environ, GIT_COMMITTER_DATE=f"@{int(time.time() + when)}", GIT_AUTHOR_DATE=f"@{int(time.time() + when)}")
        subprocess.run(["git", "-C", str(self.project), "commit", "-q", "-m", message], check=True, env=env)

    def run_script(self):
        done = subprocess.run([sys.executable, str(SCRIPT), str(self.project), str(self.session)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_nothing_changed(self):
        self.init_git()
        self.write("src/Desk.java", -200)
        self.commit("Add desk", -200)
        self.assertIn("Nothing changed", self.run_script())

    def test_uncommitted_edit_and_new_file_are_listed(self):
        self.init_git()
        self.write("src/Desk.java", -200)
        self.commit("Add desk", -200)
        self.write("src/Desk.java", -10, "edited")
        self.write("src/Room.java", -10)
        out = self.run_script()
        self.assertRegex(out, r"modified\s+src/Desk\.java")
        self.assertRegex(out, r"new\s+src/Room\.java")

    def test_commits_made_since_are_listed_with_their_files(self):
        self.init_git()
        self.write("src/Desk.java", -200)
        self.write("src/Old.java", -200)
        self.commit("Add desk", -200)
        self.write("src/Desk.java", -50, "edited")
        (self.project / "src" / "Old.java").unlink()
        self.commit("Rework desk", -50)
        out = self.run_script()
        self.assertIn("Rework desk", out)
        self.assertNotIn("Add desk", out)
        self.assertRegex(out, r"modified\s+src/Desk\.java")
        self.assertRegex(out, r"deleted\s+src/Old\.java")

    def test_files_untouched_since_are_not_listed(self):
        self.init_git()
        self.write("src/Desk.java", -200)
        self.write("src/Room.java", -200)
        self.commit("Add both", -200)
        self.write("src/Desk.java", -10, "edited")
        self.assertNotIn("Room.java", self.run_script())

    def test_ignored_files_and_the_session_folder_are_not_listed(self):
        self.init_git()
        self.write("build/out.class", -10)
        self.write(".claude/sessions/other-session.md", -10)
        out = self.run_script()
        self.assertNotIn("out.class", out)
        self.assertNotIn("other-session", out)

    def test_changed_artifacts_are_called_out(self):
        self.init_git()
        self.write("business-rules.md", -200)
        self.write("specs/001-book-a-desk.md", -200)
        self.commit("Add artifacts", -200)
        self.write("specs/001-book-a-desk.md", -10, "edited")
        out = self.run_script()
        self.assertRegex(out, r"(?s)artifacts.*specs/001-book-a-desk\.md")
        self.assertNotRegex(out, r"(?s)artifacts.*business-rules\.md")

    def test_a_project_without_git_is_compared_by_file_time(self):
        self.write("src/Desk.java", -200)
        self.write("src/Room.java", -10)
        self.write("node_modules/x/index.js", -10)
        out = self.run_script()
        self.assertRegex(out, r"changed\s+src/Room\.java")
        self.assertNotIn("Desk.java", out)
        self.assertNotIn("node_modules", out)


if __name__ == "__main__":
    unittest.main()
