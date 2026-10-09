"""Tests for session_check.py: the PostToolUse hook that tells the model when a session file it has just written
no longer has the shape EXECUTION.md defines.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"

GOOD = """# implement session — book-a-desk

## Task

- **Statement:** Book a desk.
- **Entry point:** `implement`

## Status

- **State:** `active`
- **Last updated:** 2026-10-08 10:00

## Call stack

    implement (active)
      scenario-new-use-case (active)
        locate-target (done)
        tdd-loop (active — first cycle)
          cover-batch (active — batch 2 of 3)
          finish-loop (pending)
      -> hand-off: domain-design (pending)

## Directives in effect

| Id         | Source             | Version |
|------------|--------------------|---------|
| test-style | craftsman-workshop | fd20b3c |

## Checkpoint log

### 1. `locate-target`

- **Asked:** Target module `booking`?
- **Answer:** Yes.
- **Actor:** human:dev

### 2. `enumerate-test-cases`

- **Asked:** Three stubs listed, all red.

## Parked

None.

## Next

- **Next:** cover-batch, batch 2 of 3.
"""


class SessionCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.sessions = self.tmp / ".claude" / "sessions"
        self.sessions.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def check(self, text, name="implement-session-book-a-desk.md", folder=None, tool="Edit"):
        path = (folder or self.sessions) / name
        path.write_text(text)
        payload = {"hook_event_name": "PostToolUse", "tool_name": tool, "cwd": str(self.tmp),
                   "tool_input": {"file_path": str(path)}, "session_id": "s1"}
        done = subprocess.run([sys.executable, str(SCRIPTS / "session_check.py")], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return None
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]

    def assert_problem(self, text, *phrases):
        context = self.check(text)
        self.assertIsNotNone(context, "expected a problem, got none")
        for phrase in phrases:
            self.assertIn(phrase, context)

    def test_a_well_formed_session_file_says_nothing(self):
        self.assertIsNone(self.check(GOOD))

    def test_other_files_are_not_checked(self):
        self.assertIsNone(self.check("not a session", name="notes.md", folder=self.tmp))

    def test_an_older_format_session_is_left_alone(self):
        old = GOOD.replace("- **State:** `active`\n- **Last updated:** 2026-10-08 10:00", "`active` — last updated 2026-09-19")
        self.assertIsNone(self.check(old.replace("    implement (active)", "implement > broken")))

    def test_unknown_state(self):
        self.assert_problem(GOOD.replace("`active`\n- **Last", "`in progress`\n- **Last"), "State", "active", "blocked", "done")

    def test_missing_section(self):
        self.assert_problem(GOOD.replace("## Parked\n\nNone.\n\n", ""), "## Parked")

    def test_missing_next_line(self):
        self.assert_problem(GOOD.replace("- **Next:** cover-batch, batch 2 of 3.\n", "Carry on.\n"), "**Next:**")

    def test_call_stack_line_without_a_status(self):
        self.assert_problem(GOOD.replace("locate-target (done)", "locate-target — done"), "Call stack", "locate-target")

    def test_call_stack_with_an_unknown_status(self):
        self.assert_problem(GOOD.replace("finish-loop (pending)", "finish-loop (todo)"), "finish-loop", "todo")

    def test_call_stack_that_skips_a_level(self):
        self.assert_problem(GOOD.replace("          cover-batch (active", "              cover-batch (active"),
                            "cover-batch", "two spaces")

    def test_a_done_run_with_a_step_still_active(self):
        self.assert_problem(GOOD.replace("- **State:** `active`", "- **State:** `done`"), "done", "still")

    def test_checkpoint_numbers_out_of_order(self):
        self.assert_problem(GOOD.replace("### 2. `enumerate-test-cases`", "### 3. `enumerate-test-cases`"), "### 3.", "2")

    def test_checkpoint_entry_without_asked(self):
        self.assert_problem(GOOD.replace("- **Asked:** Target module `booking`?\n", ""), "### 1.", "**Asked:**")

    def test_answer_without_actor(self):
        self.assert_problem(GOOD.replace("- **Actor:** human:dev\n", ""), "### 1.", "**Actor:**")

    def test_every_problem_is_reported_with_its_line(self):
        broken = GOOD.replace("finish-loop (pending)", "finish-loop (todo)").replace("- **Actor:** human:dev\n", "")
        context = self.check(broken)
        self.assertIn("finish-loop", context)
        self.assertIn("**Actor:**", context)
        self.assertRegex(context, r"line \d+")

    def check_after_bash(self, command, cwd=None):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(cwd or self.tmp),
                   "tool_input": {"command": command}, "session_id": "s1"}
        done = subprocess.run([sys.executable, str(SCRIPTS / "session_check.py")], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return None
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]

    def broken_session(self, name="implement-session-book-a-desk.md"):
        path = self.sessions / name
        path.write_text(GOOD.replace("finish-loop (pending)", "finish-loop (todo)"))
        return path

    def test_a_session_file_broken_by_a_shell_command_is_reported(self):
        self.broken_session()
        context = self.check_after_bash("python3 fix.py .claude/sessions/implement-session-book-a-desk.md")
        self.assertIn("implement-session-book-a-desk.md", context)
        self.assertIn("todo", context)

    def test_a_shell_command_run_from_elsewhere_is_followed_into_the_project(self):
        self.broken_session()
        elsewhere = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere)
        for command in (f"cd {self.tmp} && sed -i '' s/a/b/ .claude/sessions/implement-session-book-a-desk.md",
                        f"echo x >> {self.sessions}/implement-session-book-a-desk.md"):
            self.assertIn("todo", self.check_after_bash(command, cwd=elsewhere) or "", command)

    def test_a_shell_command_that_does_not_name_the_sessions_folder_is_not_checked(self):
        self.broken_session()
        self.assertIsNone(self.check_after_bash("mvn -q test"))

    def test_a_session_file_not_written_lately_is_not_reported_after_a_shell_command(self):
        path = self.broken_session()
        long_ago = path.stat().st_mtime - 3600
        os.utime(path, (long_ago, long_ago))
        self.assertIsNone(self.check_after_bash("ls .claude/sessions/"))

    def test_a_well_formed_session_file_says_nothing_after_a_shell_command(self):
        (self.sessions / "implement-session-book-a-desk.md").write_text(GOOD)
        self.assertIsNone(self.check_after_bash("cat .claude/sessions/implement-session-book-a-desk.md"))

    def test_a_path_held_in_a_shell_variable_falls_back_to_the_project_folder(self):
        self.broken_session()
        context = self.check_after_bash('F="$ROOT/.claude/sessions/implement-session-book-a-desk.md"; echo x >> "$F"')
        self.assertIn("todo", context or "")

    def test_a_variable_assigned_in_the_command_is_followed(self):
        self.broken_session()
        elsewhere = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere)
        command = f'P={self.tmp} && echo x >> "$P/.claude/sessions/implement-session-book-a-desk.md"'
        self.assertIn("todo", self.check_after_bash(command, cwd=elsewhere) or "")
        command = f'P="{self.tmp}"; touch ${{P}}/.claude/sessions/implement-session-book-a-desk.md'
        self.assertIn("todo", self.check_after_bash(command, cwd=elsewhere) or "")


if __name__ == "__main__":
    unittest.main()
