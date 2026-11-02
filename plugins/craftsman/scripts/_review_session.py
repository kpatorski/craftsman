"""The Claude session the dashboard server runs for one review -- see REVIEW.md. The page is the console: the server
starts `claude -p` with stream-json in and out, keeps every event in the review's `session.jsonl` for the page to
show, and passes the review's inbox into the session one message at a time, each after the previous turn ended.

A headless session cannot ask for permission, so it runs with `--permission-mode dontAsk` and a fixed tool list: the
review reads code, runs git, gh and the craftsman scripts, writes its own session file, and starts subagents. A tool
outside the list comes back as a refusal the console shows, and the session goes on.
"""
import json
import os
import pathlib
import shutil
import subprocess
import threading
import time

import _checkout as checkouts
import _reviews as reviews
import review_state

SCRIPTS = pathlib.Path(__file__).resolve().parent
# A `Bash(<prefix>:*)` rule matches whole words of the command, so each script is named by its full path, after
# `python3` and after the interpreter's own full path -- the agent writes either.
PYTHONS = list(dict.fromkeys(["python3"] + [path for path in [shutil.which("python3")] if path]))
ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Agent", "Skill", "TodoWrite", "Bash(git:*)", "Bash(gh:*)"] + [
    f"Bash({python} {script}:*)" for script in sorted(SCRIPTS.glob("*.py")) if not script.name.startswith("_")
    for python in PYTHONS]


def allowed_tools(checkout):
    """The fixed list, plus writing the checkout's craftsman session files -- by absolute path (`//`), the form a
    headless session matches against the absolute paths the agent writes to."""
    sessions = f"/{pathlib.Path(checkout).resolve()}/.claude/sessions/**"
    return ALLOWED_TOOLS + [f"Write({sessions})", f"Edit({sessions})"]


def claude_command():
    return os.environ.get("CRAFTSMAN_CLAUDE", "claude").split()


def still_running(stats):
    """Subagents a turn started in the background that have not finished: the counts are for the whole session."""
    killed = stats.get("killed") or {}
    ended = stats.get("completed", 0) + stats.get("failed", 0) + sum(killed.values() if isinstance(killed, dict) else [killed])
    return max(0, stats.get("spawned", 0) - ended)


class ReviewSession:
    """One review's session. It runs in the developer's checkout of the repository, given when the review starts and
    read from `review.json` when it resumes."""

    def __init__(self, review_id, checkout=None, command=None):
        self.review = reviews.reviews_root() / review_id
        self.checkout = pathlib.Path(checkout) if checkout else None
        self.command = command or claude_command()
        self.process = None
        self.lock = threading.Lock()
        self.turn = False
        self.background = 0
        self.delivered = set()
        self.reader = None
        self.restoring = False
        self.problem = None

    # ---- lifecycle ----------------------------------------------------------------------------------------------

    def start(self, source):
        """A new review: the session opens it with the review command, naming the review's folder and the checkout."""
        self.spawn([])
        self.send(f"/craftsman:pr-review --headless {source} --review {self.review} --checkout {self.checkout}")

    def resume(self):
        """The same conversation again, e.g. after the server restarted; what it has not handled is passed first. A
        missing clone or worktree is made again first, in the background, while `restoring` says so."""
        state = review_state.read(self.review)
        session = state.get("session")
        self.checkout = pathlib.Path(state["checkout"]) if state.get("checkout") else self.checkout
        if self.checkout is None or not (self.checkout.is_dir() or checkouts.is_clone(self.checkout)):
            raise review_state.Refused(f"the checkout of {self.review.name} is missing: {self.checkout}")
        argv = ["--resume", session] if session else []
        if not checkouts.needs_restore(self.review):
            self.spawn(argv)
            self.deliver()
            return
        self.restoring, self.problem = True, None
        threading.Thread(target=self.restore_then_spawn, args=(argv,), daemon=True).start()

    def restore_then_spawn(self, argv):
        try:
            checkouts.restore(self.review)
        except review_state.Refused as refusal:
            self.problem = str(refusal)
        try:
            if self.checkout.is_dir():
                self.spawn(argv)
        finally:
            self.restoring = False  # only now, so the page never sees a gap between restoring and running
        self.deliver()

    def stop(self):
        process, reader = self.process, self.reader
        if process and process.poll() is None:
            process.stdin.close()
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if reader:
            reader.join(timeout=10)
        with self.lock:
            self.turn = False

    def running(self):
        return self.process is not None and self.process.poll() is None

    def busy(self):
        with self.lock:
            return self.turn

    def working(self):
        """In a turn, or between turns while subagents it started in the background still run."""
        with self.lock:
            return self.running() and (self.turn or self.background > 0)

    def quiet(self):
        """Seconds since the session last wrote an event, or None when it has written none."""
        transcript = self.review / "session.jsonl"
        return round(time.time() - transcript.stat().st_mtime) if transcript.exists() else None

    # ---- talking to the session ---------------------------------------------------------------------------------

    def deliver(self):
        """Pass the next inbox message the session has not handled, when it is not in the middle of a turn."""
        if not self.running() or self.busy() or not (self.review / "review.json").exists():
            return
        waiting = [m for m in reviews.pending_messages(self.review) if m["id"] not in self.delivered]
        if waiting:
            message = waiting[0]
            self.delivered.add(message["id"])
            self.send(f"Message {message['id']} from the review page:\n```json\n{json.dumps(message)}\n```\n"
                      f"Handle it as serve-page says, then record it: "
                      f"python3 {SCRIPTS}/review_state.py {self.review} handled {message['id']}\n"
                      f"A review_state.py payload is one JSON argument in single quotes, never a heredoc or a pipe.")

    def send(self, text):
        with self.lock:
            self.turn = True
            line = json.dumps({"type": "user", "message": {"role": "user", "content": text}})
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()

    def spawn(self, extra):
        self.review.mkdir(parents=True, exist_ok=True)
        self.delivered = set()
        self.background = 0
        argv = self.command + ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                               "--replay-user-messages",
                               "--permission-mode", "dontAsk", "--allowedTools", *allowed_tools(self.checkout)] + extra
        errors = (self.review / "session.stderr").open("a")
        self.process = subprocess.Popen(argv, cwd=self.checkout, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=errors, text=True, bufsize=1)
        errors.close()
        self.reader = threading.Thread(target=self.read, args=(self.process,), daemon=True)
        self.reader.start()

    def read(self, process):
        """Keep every event for the console; at the end of each turn, record the session id and go on with the inbox."""
        session = None
        with (self.review / "session.jsonl").open("a") as transcript:
            for line in process.stdout:
                if not line.strip():
                    continue
                transcript.write(line if line.endswith("\n") else line + "\n")
                transcript.flush()
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                session = event.get("session_id") or session
                if event.get("type") == "result":
                    self.record_session(session)
                    with self.lock:
                        self.turn = False
                        self.background = still_running(event.get("subagent_stats") or {})
                    if self.closed():
                        process.stdin.close()
                        checkouts.release(self.review)
                    else:
                        self.deliver()
        process.stdout.close()
        with self.lock:
            self.turn = False

    def closed(self):
        return (self.review / "review.json").exists() and bool(review_state.read(self.review).get("closed"))

    def record_session(self, session):
        if session and (self.review / "review.json").exists():
            if review_state.read(self.review).get("session") != session:
                review_state.change(self.review, "set", {"session": session})
