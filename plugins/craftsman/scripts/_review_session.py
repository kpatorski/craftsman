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
import subprocess
import threading

import _reviews as reviews
import review_state

SCRIPTS = pathlib.Path(__file__).resolve().parent
ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Agent", "Skill", "TodoWrite", "Bash(git:*)", "Bash(gh:*)",
                 f"Bash(python3 {SCRIPTS}/:*)", "Write(.claude/sessions/**)", "Edit(.claude/sessions/**)"]


def claude_command():
    return os.environ.get("CRAFTSMAN_CLAUDE", "claude").split()


class ReviewSession:
    def __init__(self, project, review_id, command=None):
        self.project = pathlib.Path(project)
        self.review = reviews.reviews_root(project) / review_id
        self.command = command or claude_command()
        self.process = None
        self.lock = threading.Lock()
        self.turn = False
        self.delivered = set()
        self.reader = None

    # ---- lifecycle ----------------------------------------------------------------------------------------------

    def start(self, source):
        """A new review: the session opens it with the review command."""
        self.spawn([])
        self.send(f"/craftsman:pr-review --headless {source}")

    def resume(self):
        """The same conversation again, e.g. after the server restarted; what it has not handled is passed first."""
        session = review_state.read(self.review).get("session")
        self.spawn(["--resume", session] if session else [])
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
                      f"python3 {SCRIPTS}/review_state.py {self.review} handled {message['id']}")

    def send(self, text):
        with self.lock:
            self.turn = True
            line = json.dumps({"type": "user", "message": {"role": "user", "content": text}})
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()

    def spawn(self, extra):
        self.review.mkdir(parents=True, exist_ok=True)
        self.delivered = set()
        argv = self.command + ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                               "--replay-user-messages",
                               "--permission-mode", "dontAsk", "--allowedTools", *ALLOWED_TOOLS] + extra
        errors = (self.review / "session.stderr").open("a")
        self.process = subprocess.Popen(argv, cwd=self.project, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
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
                    if self.closed():
                        process.stdin.close()
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
