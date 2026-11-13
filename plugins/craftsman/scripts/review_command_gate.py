#!/usr/bin/env python3
"""Hook: in a review's session, every shell command is weighed here, by rule, never by the model -- see REVIEW.md,
"The review's session".

PreToolUse on Bash, only in the session the dashboard server starts for a review (`CRAFTSMAN_RUN=pr-review`, with the
review folder in `CRAFTSMAN_REVIEW`). What the developer types or dictates, and what the pull request says, reaches the
model; a misheard sentence or a planted instruction can make it want a command. The decision does not rest on it:

- `allow` -- git and gh that only read, preparing the review (fetching the reviewed commits, the review's worktree),
  and the review's own scripts; such commands may be chained with `&&`, `||`, `;` and piped into head, tail or wc;
- `deny` -- anything that publishes or changes the repository: git push, merge, reset, commit, ...; gh that writes
  to GitHub or reveals the login; sending the review, which is the server's job when the developer presses Send;
- no decision -- everything else, and every command the rules cannot read with certainty (redirections, `$(...)`,
  several lines, a variable before the command): the session's permission rules decide, and the session's own list
  allows no git, no gh and no script outside REVIEW_SCRIPTS, so such a command waits for the developer on the review
  page -- unless the developer allowed it there for every review (`review-tools`).

A gate that does not run, or fails, therefore leaves every git, gh or script command to the developer, never to the
model.
"""
import json
import os
import pathlib
import shlex
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent
# the scripts a review's session runs (the code-review protocols and EXECUTION.md name them)
REVIEW_SCRIPTS = ("review_state.py", "review_directives.py", "github_conversation.py", "fix_prompts.py",
                  "changed_since.py", "render_diff.py", "model_tiers.py", "refresh_review.py",
                  "dedupe_findings.py", "verify_quotes.py", "plugin_version.py")
PYTHONS = ("python3", "python")
CHAIN = {"&&", "||", ";", "|"}
PIPE_FILTERS = {"head", "tail", "wc"}

GIT_READS = {"diff", "log", "show", "rev-parse", "merge-base", "ls-files", "ls-tree", "cat-file", "blame", "grep",
             "status", "rev-list", "describe", "name-rev", "shortlog", "for-each-ref", "show-ref", "diff-tree",
             "range-diff", "whatchanged"}
GIT_WRITES = {"push", "merge", "rebase", "reset", "commit", "cherry-pick", "revert", "am", "apply", "clean", "rm",
              "mv", "stash", "pull", "gc", "prune", "filter-branch", "filter-repo", "update-ref", "symbolic-ref",
              "notes", "submodule", "restore", "switch", "init", "clone", "send-email", "credential", "replace",
              "bisect", "add", "update-index", "reflog"}
GH_READS = {("pr", "view"), ("pr", "list"), ("pr", "diff"), ("pr", "checks"), ("pr", "status"), ("repo", "view"),
            ("issue", "view"), ("issue", "list"), ("run", "view"), ("run", "list")}
GH_WRITES = {"release", "secret", "variable", "auth", "ssh-key", "gpg-key", "gist", "label", "cache", "codespace",
             "extension", "alias", "config", "workflow", "ruleset", "attestation", "org", "project"}
GH_WRITE_ACTIONS = {"merge", "close", "comment", "review", "edit", "create", "ready", "reopen", "lock", "unlock",
                    "delete", "archive", "unarchive", "rename", "fork", "sync", "transfer", "pin", "unpin", "rerun",
                    "cancel", "develop", "update-branch", "set-default", "deploy-key", "disable", "enable", "run"}
GH_API_VALUES = {"--jq", "-q", "--template", "-t", "-H", "--header", "--cache", "--hostname", "-X", "--method"}
GH_API_FLAGS = {"--paginate", "-i", "--include", "--silent", "--slurp", "--verbose"}

ALLOW, ASK, DENY = "allow", "ask", "deny"
RANK = {ALLOW: 0, ASK: 1, DENY: 2}


class Verdict:
    def __init__(self, decision, why=""):
        self.decision, self.why = decision, why


def under(path, folder):
    try:
        return pathlib.Path(path).resolve().is_relative_to(pathlib.Path(folder).resolve())
    except (OSError, ValueError):
        return False


def split(command):
    """The command's simple commands and the operators between them, or None when the rules cannot read it."""
    if not command.strip() or "\n" in command or "`" in command or "$(" in command or "<(" in command:
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    parts, current, operators = [], [], []
    for token in tokens:
        if token in CHAIN:
            if not current:
                return None
            parts.append(current)
            operators.append(token)
            current = []
        elif token and set(token) <= set("&|;<>()"):
            return None  # redirection, background, subshell
        else:
            current.append(token)
    if not current:
        return None
    parts.append(current)
    return parts, operators


def git(words, review):
    args, worktree = words[1:], None
    while args and args[0].startswith("-"):
        if args[0] == "-C" and len(args) > 1:
            worktree, args = args[1], args[2:]
        elif args[0] in ("--no-pager", "-P"):
            args = args[1:]
        elif args[0] == "-c" or args[0].startswith(("--config-env", "--exec-path")):
            return Verdict(DENY, "git -c and --exec-path can make git run a program")
        else:
            return Verdict(ASK)
    if not args:
        return Verdict(ASK)
    sub, rest = args[0], args[1:]
    if sub in GIT_WRITES:
        return Verdict(DENY, f"git {sub} changes the repository or publishes it")
    if sub in GIT_READS:
        for arg in rest:
            if arg.startswith("--output="):
                if not review or not under(arg.split("=", 1)[1], review):
                    return Verdict(ASK)
            elif arg == "--output" or arg.startswith(("-O", "--open-files-in-pager", "--ext-diff")):
                return Verdict(ASK)
        return Verdict(ALLOW)
    if sub == "branch":
        if any(arg in ("-d", "-D", "-m", "-M", "-c", "-C", "-f", "--delete", "--move", "--copy", "--force", "-u",
                       "--set-upstream-to", "--unset-upstream", "--edit-description") for arg in rest):
            return Verdict(DENY, "git branch with that option changes the repository")
        listing = {"--list", "-l", "-a", "--all", "-r", "--remotes", "--show-current", "--contains", "--merged",
                   "--no-merged", "-v", "-vv"}
        return Verdict(ALLOW if not rest or rest[0] in listing else ASK)
    if sub == "tag":
        return Verdict(ALLOW if not rest or rest[0] in ("-l", "--list") else DENY, "git tag changes the repository")
    if sub == "remote":
        if not rest or rest[0] in ("-v", "--verbose", "show", "get-url"):
            return Verdict(ALLOW)
        return Verdict(DENY, "git remote with that action changes where the repository pushes")
    if sub == "config":
        if rest and rest[0] in ("--get", "--get-all", "--get-regexp", "--list", "-l"):
            return Verdict(ALLOW)
        return Verdict(DENY, "git config can make git run a program")
    if sub == "worktree":
        if rest[:1] == ["list"]:
            return Verdict(ALLOW)
        options = [arg for arg in rest[1:] if arg.startswith("-")]
        places = [arg for arg in rest[1:] if not arg.startswith("-")]
        if rest[:1] == ["add"] and set(options) <= {"--detach", "-q", "--quiet"} and "--detach" in options and \
                len(places) == 2 and review and under(places[0], pathlib.Path(review) / "worktree"):
            return Verdict(ALLOW)
        return Verdict(ASK)
    if sub == "fetch":
        if any(arg.startswith(("--upload-pack", "--exec")) for arg in rest):
            return Verdict(DENY, "git fetch --upload-pack runs a program")
        refs = [arg for arg in rest if not arg.startswith("-")]
        if set(arg for arg in rest if arg.startswith("-")) <= {"-q", "--quiet", "--no-tags"} and \
                refs[:1] == ["origin"] and not any(":" in ref for ref in refs[1:]):
            return Verdict(ALLOW)
        return Verdict(ASK)
    if sub == "checkout":
        options = {arg for arg in rest if arg.startswith("-")}
        if worktree and review and under(worktree, pathlib.Path(review) / "worktree") and "--detach" in options and \
                options <= {"--detach", "-q", "--quiet"} and len(rest) - len(options) == 1:
            return Verdict(ALLOW)
        return Verdict(ASK)
    return Verdict(ASK)


def gh(words):
    args = words[1:]
    while len(args) > 1 and args[0] in ("-R", "--repo"):
        args = args[2:]
    if not args:
        return Verdict(ASK)
    if args[0] in GH_WRITES:
        return Verdict(DENY, f"gh {args[0]} writes to GitHub or reveals the login")
    if args[0] == "api":
        return gh_api(args[1:])
    if len(args) > 1:
        if (args[0], args[1]) in GH_READS:
            return Verdict(ALLOW)
        if args[1] in GH_WRITE_ACTIONS:
            return Verdict(DENY, f"gh {args[0]} {args[1]} writes to GitHub")
    return Verdict(ASK)


def gh_api(args):
    endpoints, i = [], 0
    while i < len(args):
        arg = args[i]
        name, _, inline = arg.partition("=")
        if name in ("-X", "--method"):
            method = inline or (args[i + 1] if i + 1 < len(args) else "")
            if method.upper() != "GET":
                return Verdict(DENY, f"gh api {method} writes to GitHub")
            i += 1 if inline else 2
        elif name in ("-f", "-F", "--field", "--raw-field", "--input"):
            return Verdict(ASK if endpoints == ["graphql"] else DENY, "gh api with fields sends a POST to GitHub")
        elif name in GH_API_VALUES:
            i += 1 if inline else 2
        elif arg in GH_API_FLAGS:
            i += 1
        elif arg.startswith("-"):
            return Verdict(ASK)
        else:
            endpoints.append(arg)
            i += 1
    return Verdict(ALLOW if len(endpoints) == 1 and endpoints[0] != "graphql" else ASK)


def python(words):
    if len(words) < 2 or words[1].startswith("-"):
        return Verdict(ASK)
    script = pathlib.Path(words[1])
    if script.parent.resolve() != SCRIPTS:
        return Verdict(ASK)
    if script.name == "send_review.py":
        return Verdict(DENY, "sending the review is the dashboard server's job, when the developer presses Send")
    return Verdict(ALLOW if script.name in REVIEW_SCRIPTS else ASK)


def weigh(words, review, piped):
    head = words[0]
    if head == "git":
        return git(words, review)
    if head == "gh":
        return gh(words)
    if head in PYTHONS or pathlib.Path(head).name in PYTHONS:
        return python(words) if head in PYTHONS else Verdict(ASK)
    if piped and head in PIPE_FILTERS and all(word.startswith("-") or word.isdigit() for word in words[1:]):
        return Verdict(ALLOW)
    return Verdict(ASK)


def decide(command, review):
    found = split(command)
    if found is None:
        return Verdict(ASK)
    parts, operators = found
    verdicts = [weigh(words, review, piped=i > 0 and operators[i - 1] == "|") for i, words in enumerate(parts)]
    return max(verdicts, key=lambda verdict: RANK[verdict.decision])


def answer(verdict):
    """The hook's output, or None to leave the command to the session's permission rules."""
    if verdict.decision == ASK:
        return None
    reason = {
        ALLOW: "craftsman review: a read-only command",
        DENY: f"craftsman review: refused -- {verdict.why}. A review's session is read-only: it reads the change "
              f"and the pull request, and the developer publishes. If the developer asked for this, tell them to "
              f"run it themselves.",
    }[verdict.decision]
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": verdict.decision,
                                   "permissionDecisionReason": reason}}


def main():
    if os.environ.get("CRAFTSMAN_RUN") != "pr-review":
        return
    try:
        payload = json.load(sys.stdin)
        if payload.get("hook_event_name") != "PreToolUse" or payload.get("tool_name") != "Bash":
            return
        verdict = decide(str((payload.get("tool_input") or {}).get("command") or ""),
                         os.environ.get("CRAFTSMAN_REVIEW"))
    except Exception as error:  # a gate that cannot decide leaves the command to the permission rules
        print(f"craftsman review gate: {error}", file=sys.stderr)
        return
    output = answer(verdict)
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
