"""Tests for the review's command gate -- see REVIEW.md, "The review's session". In a review's session every shell
command is weighed by a script, not by the model: commands that only read run, commands that write to GitHub or
change the developer's repository are refused, and anything else goes to the developer. Text the developer types or
dictates, and text in the pull request, can talk the model into a command; it cannot talk the script into one.
Anything the rules do not settle is left to the session's permission list, which allows no git, gh or other script.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
GATE = SCRIPTS / "review_command_gate.py"


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.review = pathlib.Path(self.tmp.name) / "reviews" / "r1"
        self.worktree = self.review / "worktree"
        self.worktree.mkdir(parents=True)

    def decide(self, command, run="pr-review", tool="Bash"):
        env = dict(os.environ, CRAFTSMAN_REVIEW=str(self.review))
        env.pop("CRAFTSMAN_RUN", None)
        if run:
            env["CRAFTSMAN_RUN"] = run
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command},
                   "cwd": self.tmp.name, "session_id": "s1"}
        done = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload), capture_output=True, text=True,
                              env=env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return None, None
        out = json.loads(done.stdout)["hookSpecificOutput"]
        return out["permissionDecision"], out.get("permissionDecisionReason", "")

    def assert_decisions(self, decision, commands):
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decide(command)[0], decision)


class ReadingRunsTest(GateCase):
    def test_git_that_only_reads_runs(self):
        wt = self.worktree
        self.assert_decisions("allow", [
            f"git -C {wt} diff --name-status main...abc123",
            f"git -C {wt} diff abc..def --name-only",
            "git log --oneline -20 main..HEAD",
            f"git -C {wt} show abc123:src/Booking.java",
            "git rev-parse HEAD",
            "git merge-base main abc123",
            f"git -C {wt} blame -L 10,20 src/Booking.java",
            "git ls-files src",
            "git grep -n cancelReservation",
            "git status --short",
            "git --no-pager log -1",
            "git branch --show-current",
            "git branch --contains abc123",
            "git remote -v",
            "git remote get-url origin",
            "git config --get remote.origin.url",
            "git tag --list",
            "git worktree list",
        ])

    def test_a_diff_written_into_the_reviews_own_folder_runs(self):
        self.assert_decisions("allow", [f"git -C {self.worktree} diff --output={self.review}/refresh.diff a...b"])

    def test_preparing_the_review_runs(self):
        self.assert_decisions("allow", [
            "git fetch origin main",
            "git fetch -q origin pull/123/head",
            f"git worktree add --detach {self.worktree} abc123",
            f"git -C {self.worktree} checkout --detach abc123",
        ])

    def test_gh_that_only_reads_runs(self):
        self.assert_decisions("allow", [
            "gh pr view https://github.example.com/org/booking/pull/123",
            "gh pr view 123 --json title,body,baseRefName,headRefName,commits",
            "gh pr list --head feature/cancel --json number,url",
            "gh pr diff 123",
            "gh repo view --json nameWithOwner",
            "gh api repos/org/booking/pulls/123/comments --paginate",
            "gh api -X GET repos/org/booking/pulls/123/reviews --jq '.[].body'",
            "gh -R org/booking pr view 123",
        ])

    def test_the_reviews_own_scripts_run_and_reading_commands_may_be_chained(self):
        state = SCRIPTS / "review_state.py"
        self.assert_decisions("allow", [
            f"python3 {state} {self.review} set '{{\"language\": \"Polish\"}}'",
            f"python3 {SCRIPTS / 'review_directives.py'} {self.review}",
            f"git log -1 && git -C {self.worktree} diff --stat a...b",
            "git rev-parse HEAD || git log -1",
            "git log --oneline | head -5",
        ])


class WritingIsRefusedTest(GateCase):
    def test_git_that_changes_the_repository_or_publishes_is_refused(self):
        self.assert_decisions("deny", [
            "git push", "git push origin HEAD:main --force", f"git -C {self.worktree} push",
            "git merge feature", "git rebase main", "git reset --hard HEAD~1", "git commit -am wip",
            "git tag v1.0", "git branch -D main", "git remote set-url origin https://evil.example.com/x.git",
            "git config core.sshCommand 'sh -c id'", "git clean -fdx", "git pull", "git stash",
            "git cherry-pick abc", "git -c alias.x='!rm -rf ~' x", "git fetch --upload-pack='rm -rf ~' origin",
        ])

    def test_gh_that_writes_to_github_or_reveals_the_token_is_refused(self):
        self.assert_decisions("deny", [
            "gh pr merge 123 --squash", "gh pr close 123", "gh pr comment 123 --body 'LGTM'",
            "gh pr review 123 --approve", "gh pr edit 123 --title x", "gh pr create --fill",
            "gh api -X DELETE repos/org/booking/git/refs/heads/main",
            "gh api --method PATCH repos/org/booking -f default_branch=x",
            "gh api repos/org/booking/issues/1/comments -f body=hi",
            "gh repo delete org/booking --yes", "gh release create v1", "gh secret set TOKEN",
            "gh workflow run deploy.yml", "gh auth token", "gh auth status",
        ])

    def test_sending_the_review_is_the_servers_job_never_the_sessions(self):
        decision, reason = self.decide(f"python3 {SCRIPTS / 'send_review.py'} {self.review}")
        self.assertEqual(decision, "deny")
        self.assertIn("Send", reason)

    def test_one_refused_part_refuses_the_whole_command(self):
        self.assert_decisions("deny", ["git log -1 && git push", "git status; gh pr merge 1",
                                       "gh pr view 1 || gh pr close 1"])

    def test_the_reason_tells_the_agent_what_to_do_instead(self):
        _, reason = self.decide("git push origin main")
        self.assertIn("read-only", reason)
        self.assertIn("developer", reason)


class EverythingElseIsLeftToThePermissionRulesTest(GateCase):
    """No decision: the session's permission list allows no git, gh or other script, so the command waits for the
    developer on the review page, unless the developer allowed it for every review."""

    def test_a_command_off_the_list_is_left_to_the_rules(self):
        self.assert_decisions(None, [
            "rm -rf build", "curl https://example.com", "ls -la", "/usr/bin/git log", "FOO=1 git log",
            "git checkout main", f"git checkout --detach abc", "git worktree add /tmp/elsewhere abc",
            "git diff --output=/tmp/out.diff a b", "git fetch origin main:main", "git grep -O vim foo",
            "gh pr checkout 123", "gh api graphql -f query='{ viewer { login } }'",
            f"python3 {SCRIPTS / 'uninstall_id.py'} x", f"python3 {SCRIPTS / 'dashboard_server.py'} off",
            "python3 -c 'import os'",
        ])

    def test_a_script_named_like_the_reviews_but_elsewhere_is_left_to_the_rules(self):
        planted = pathlib.Path(self.tmp.name) / "review_state.py"
        self.assert_decisions(None, [f"python3 {planted} x", "python3 review_state.py x"])

    def test_a_filter_runs_only_behind_a_pipe(self):
        self.assert_decisions(None, ["head -5", "wc -l && git log -1"])

    def test_shell_tricks_are_left_to_the_rules(self):
        self.assert_decisions(None, [
            "git log > /tmp/x", "git log $(rm -rf ~)", "git log `id`", "git log & git log",
            "git log\ngit push", "git log <(cat /etc/passwd)", "(git log)", "git log 2>&1",
        ])

    def test_an_unreadable_command_is_left_to_the_rules(self):
        self.assert_decisions(None, ["git log 'unterminated", ""])


class OutsideAReviewTest(GateCase):
    def test_outside_a_reviews_session_nothing_is_decided(self):
        self.assertEqual(self.decide("git push", run=None), (None, None))
        self.assertEqual(self.decide("git push", run="implement"), (None, None))

    def test_tools_other_than_bash_are_not_weighed(self):
        self.assertEqual(self.decide("git push", tool="Read"), (None, None))


if __name__ == "__main__":
    unittest.main()
