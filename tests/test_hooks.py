"""Black-box tests for the plugin's hook scripts: each runs as Claude Code would run it -- JSON on stdin, decision
on stdout -- against a scratch git repository and a scratch content tree.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"

SESSION = """# Session: book a desk

## Task

- **Statement:** Book a desk.
- **Entry point:** `implement`

## Status

- **State:** `{state}`
- **Last updated:** 2026-10-08 10:00

## Call stack

    implement (active)
      scenario-new-use-case (active)
        tdd-loop (active)
          finish-loop (active)

## Directives in effect

| Id           | Source             | Version |
|--------------|--------------------|---------|
| test-style   | craftsman-workshop | fd20b3c |
| prefer-lombok | craftsman-workshop | fd20b3c |

## Checkpoint log

### 1. `confirm-conventions`

- **Asked:** Package layout ok?
- **Answer:** Yes.
- **Actor:** human:dev
{last_entry}
## Parked

None.

- **Next:** finish-loop checkpoint.
"""

ANSWERED = """
### 2. `finish-loop`

- **Asked:** Use case done. Commit it, or more changes first?
- **Answer:** Commit it.
- **Actor:** human:dev
"""

UNANSWERED = """
### 2. `finish-loop`

- **Asked:** Use case done. Commit it, or more changes first?
"""


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.project = self.tmp / "project"
        self.project.mkdir()
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "dev@example.com")
        git(self.project, "config", "user.name", "dev")
        self.data = self.tmp / "plugin-data"
        self.content = self.tmp / "content"
        for kind, entry in (("directives", "test-style"), ("bundles/java/directives", "prefer-lombok"),
                            ("bundles/tdd/protocols", "finish-loop")):
            folder = self.content / kind / entry
            folder.mkdir(parents=True)
            (folder / ("protocol.md" if "protocols" in kind else "directive.md")).write_text(f"---\nid: {entry}\n---\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def session(self, state="active", last_entry=ANSWERED, name="implement-session-book-a-desk.md"):
        sessions = self.project / ".claude" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        path = sessions / name
        path.write_text(SESSION.format(state=state, last_entry=last_entry))
        return path

    def commit_file(self, name="a.txt"):
        (self.project / name).write_text(name)
        git(self.project, "add", name)
        git(self.project, "commit", "-q", "-m", f"Add {name}")

    def run_hook(self, script, payload):
        env = dict(os.environ, CLAUDE_PLUGIN_DATA=str(self.data), CRAFTSMAN_CONTENT_ROOT=str(self.content))
        payload = {"session_id": "s1", "cwd": str(self.project), **payload}
        done = subprocess.run([sys.executable, str(SCRIPTS / script)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else None


class CommitGateTest(HookCase):
    def human_speaks(self):
        self.run_hook("commit_gate.py", {"hook_event_name": "UserPromptSubmit", "prompt": "commit it"})

    def try_bash(self, command):
        return self.run_hook("commit_gate.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                "tool_input": {"command": command}})

    def assert_denied(self, result, *phrases):
        self.assertIsNotNone(result, "expected a deny decision, got no objection")
        out = result["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        for phrase in phrases:
            self.assertIn(phrase, out["permissionDecisionReason"])

    def test_commit_outside_a_craftsman_run_is_not_touched(self):
        self.commit_file()
        self.assertIsNone(self.try_bash("git commit -m 'x'"))

    def test_commit_in_a_finished_run_is_not_touched(self):
        self.session(state="done")
        self.commit_file()
        self.assertIsNone(self.try_bash("git commit -m 'x'"))

    def test_other_commands_are_not_touched(self):
        self.session()
        self.commit_file()
        self.assertIsNone(self.try_bash("git status && ./gradlew test"))
        self.assertIsNone(self.try_bash("git stash create"))

    def test_commit_after_the_developer_answered_is_allowed(self):
        self.session()
        self.commit_file()
        time.sleep(1.1)
        self.human_speaks()
        self.assertIsNone(self.try_bash("git commit -m 'Book a desk'"))

    def test_commit_without_the_developer_speaking_since_the_last_commit_is_denied(self):
        self.human_speaks()
        time.sleep(1.1)
        self.session()
        self.commit_file()
        self.assert_denied(self.try_bash("git commit -m 'Book a desk'"), "since the last commit", "Ask")

    def test_second_commit_needs_a_new_answer(self):
        self.session()
        self.commit_file()
        time.sleep(1.1)
        self.human_speaks()
        self.assertIsNone(self.try_bash("git commit -m 'one'"))
        self.commit_file("b.txt")
        self.assert_denied(self.try_bash("git commit -m 'two'"), "since the last commit")

    def test_an_answer_through_ask_user_question_counts(self):
        self.session()
        self.commit_file()
        time.sleep(1.1)
        self.run_hook("commit_gate.py", {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                                         "tool_input": {}, "tool_response": {}})
        self.assertIsNone(self.try_bash("git commit -m 'Book a desk'"))

    def test_unrecorded_answer_is_denied(self):
        self.session(last_entry=UNANSWERED)
        self.commit_file()
        time.sleep(1.1)
        self.human_speaks()
        self.assert_denied(self.try_bash("git commit -m 'Book a desk'"), "**Answer:**", "finish-loop")

    def test_first_commit_of_a_new_repository_still_needs_the_developer(self):
        self.session()
        self.assert_denied(self.try_bash("git commit -m 'Initial'"), "Ask")
        self.human_speaks()
        self.assertIsNone(self.try_bash("git commit -m 'Initial'"))

    def test_commit_forms_are_recognised(self):
        self.session()
        self.commit_file()
        for command in ("git -C . commit -m x", "git -c user.name=x commit --amend", "cd . && git commit -am x",
                        "git add . && git commit -F - <<'EOF'\nx\nEOF"):
            self.assert_denied(self.try_bash(command), "since the last commit")

    def test_a_blocked_run_does_not_gate_unrelated_commits(self):
        self.session(state="blocked")
        self.commit_file()
        self.assertIsNone(self.try_bash("git commit -m x"))


class ReloadAfterCompactTest(HookCase):
    def compacted(self):
        return self.run_hook("reload_after_compact.py", {"hook_event_name": "SessionStart", "source": "compact"})

    def test_nothing_without_a_craftsman_run(self):
        self.assertIsNone(self.compacted())

    def test_nothing_for_a_finished_run(self):
        self.session(state="done")
        self.assertIsNone(self.compacted())

    def test_names_session_current_step_and_every_file_to_reread(self):
        path = self.session()
        context = self.compacted()["hookSpecificOutput"]["additionalContext"]
        self.assertIn(str(path), context)
        self.assertIn("implement > scenario-new-use-case > tdd-loop > finish-loop", context)
        self.assertIn(str(self.content / "directives" / "test-style" / "directive.md"), context)
        self.assertIn(str(self.content / "bundles" / "java" / "directives" / "prefer-lombok" / "directive.md"), context)
        self.assertIn(str(self.content / "bundles" / "tdd" / "protocols" / "finish-loop" / "protocol.md"), context)
        self.assertIn("finish-loop checkpoint.", context)

    def test_reads_the_older_session_format_too(self):
        path = self.session()
        text = path.read_text()
        text = text.replace("""| Id           | Source             | Version |
|--------------|--------------------|---------|
| test-style   | craftsman-workshop | fd20b3c |
| prefer-lombok | craftsman-workshop | fd20b3c |""", """- `test-style` -- loaded by `finish-loop`.
- `prefer-lombok` -- applied at `add-dependencies`.
- All from `craftsman-workshop` @ `b0a7994`.""")
        text = text.replace("- **Next:** finish-loop checkpoint.", "## Next\n\nAsk the finish-loop checkpoint.\nThen commit.")
        path.write_text(text)
        context = self.compacted()["hookSpecificOutput"]["additionalContext"]
        self.assertIn(str(self.content / "directives" / "test-style" / "directive.md"), context)
        self.assertIn(str(self.content / "bundles" / "java" / "directives" / "prefer-lombok" / "directive.md"), context)
        self.assertNotIn("craftsman-workshop: not found", context)
        self.assertNotIn("b0a7994", context)
        self.assertIn("Ask the finish-loop checkpoint.", context)

    def test_a_directive_missing_from_the_content_is_named_not_dropped(self):
        shutil.rmtree(self.content / "directives" / "test-style")
        self.session()
        context = self.compacted()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("test-style", context)
        self.assertIn("not found", context)


if __name__ == "__main__":
    unittest.main()
