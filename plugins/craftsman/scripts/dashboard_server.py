#!/usr/bin/env python3
"""The live craftsman dashboard: a small local HTTP server (stdlib only) serving one page that stays open in a
browser -- the project's artifacts and session stacks, and the installed content -- refreshed by itself whenever a
file changes on disk. See MANAGEMENT.md, "Dashboard". The same server serves the reviews' own page, `/review`, and
runs each review's Claude session -- see REVIEW.md.

Usage:
    dashboard_server.py on|start [--project <dir>] [--content ~/.claude/craftsman] [--port 4747]
    dashboard_server.py off|stop
    dashboard_server.py remove [--project <dir>]
    dashboard_server.py status
    dashboard_server.py review --source <PR URL | target:source> [--project <repository>]   (prints its /review URL)

`start` runs the server in the background, detached from the calling shell, and prints its URL. If one is already
running, it adds the project to it instead of starting a second one -- one server, every project it was started
from. A server started by an older plugin version is replaced. The server exits by itself after 8 hours with no
page open. State lives in ~/.claude/craftsman-dashboard.json, its log in ~/.claude/craftsman-dashboard.log.

Binds 127.0.0.1 only. A write (the enable/disable switches) must come from the page itself: requests are refused
unless the Host header names this server and a custom header is present, which a page on any other origin cannot
send without a CORS preflight this server never answers.
"""
import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _dashboard_data as data  # noqa: E402
import _review_session  # noqa: E402
import _reviews as reviews  # noqa: E402
import review_state  # noqa: E402
import send_review  # noqa: E402
from _markdown import MD_CSS  # noqa: E402
from _theme import THEME_CSS  # noqa: E402

STATE = pathlib.Path.home() / ".claude" / "craftsman-dashboard.json"
LOG = pathlib.Path.home() / ".claude" / "craftsman-dashboard.log"
PAGES = {"/": HERE / "dashboard_page.html", "/review": HERE / "review_page.html"}
IDLE_EXIT_SECONDS = 8 * 3600
POLL_SECONDS = 1.0
RESCAN_EVERY = 10  # polls between looks for projects newly created inside a root


def plugin_version():
    try:
        return json.loads((data.PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()).get("version", "?")
    except (OSError, ValueError):
        return "?"


# ---- the running server ----------------------------------------------------------------------------------------

class Hub:
    """Shared state: the registered roots (`projects` -- where the dashboard was started from), the craftsman projects
    found inside them, and a change counter the watcher bumps and page streams wait on."""

    def __init__(self, content, projects, port):
        self.content = content
        self.projects = list(dict.fromkeys(projects))
        self.hidden = set()
        self.found = []
        self.rescan()
        self.port = port
        self.lock = threading.Condition()
        self.version = 0
        self.changed = []
        self.clients = 0
        self.last_client = time.time()
        self.sessions = {}

    def session(self, project, review_id):
        """The Claude session of one review, created on first use; one per review for the server's lifetime."""
        with self.lock:
            key = (str(project), review_id)
            if key not in self.sessions:
                self.sessions[key] = _review_session.ReviewSession(project, review_id)
            return self.sessions[key]

    def stop_sessions(self):
        for runner in list(self.sessions.values()):
            runner.stop()

    def rescan(self):
        """Re-discover the projects inside every root; True when the list changed."""
        found = list(dict.fromkeys(p for root in self.projects for p in data.discover_projects(root)))
        changed = found != self.found
        self.found = found
        return changed

    def project_list(self):
        return [p for p in self.found if p not in self.hidden]

    def add_project(self, project):
        with self.lock:
            self.hidden -= {p for p in self.hidden if p == project or project in p.parents}
            if project not in self.projects:
                self.projects.append(project)
            self.rescan()
            self.version += 1
            self.changed = [str(project)]
            self.lock.notify_all()
        self.save()

    def remove_project(self, project):
        """A root is forgotten with everything found inside it; a project found inside a root is hidden."""
        with self.lock:
            if project in self.projects:
                self.projects.remove(project)
                self.rescan()
            elif project in self.found:
                self.hidden.add(project)
            else:
                return False
            self.version += 1
            self.changed = [str(project)]
            self.lock.notify_all()
        self.save()
        return True

    def save(self):
        STATE.write_text(json.dumps(dict(pid=os.getpid(), port=self.port, version=plugin_version(),
                                         content=str(self.content), projects=[str(p) for p in self.projects])))

    def snapshot(self):
        stamps = {}
        for path in data.watched_paths(self.project_list(), self.content):
            try:
                stamps[str(path)] = path.stat().st_mtime
            except OSError:
                pass
        return stamps

    def watch(self, server):
        previous = self.snapshot()
        ticks = 0
        while True:
            time.sleep(POLL_SECONDS)
            ticks += 1
            with self.lock:
                new_projects = ticks % RESCAN_EVERY == 0 and self.rescan()
            current = self.snapshot()
            changed = sorted(k for k in current.keys() | previous.keys() if current.get(k) != previous.get(k))
            if new_projects:
                changed.append("(projects)")
            previous = current
            with self.lock:
                if changed:
                    self.version += 1
                    self.changed = changed
                    self.lock.notify_all()
                idle = self.clients == 0 and time.time() - self.last_client > IDLE_EXIT_SECONDS
            if idle:
                threading.Thread(target=server.shutdown, daemon=True).start()
                return


class Handler(BaseHTTPRequestHandler):
    hub = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def allowed_host(self):
        host = self.headers.get("Host", "")
        return host in (f"localhost:{self.hub.port}", f"127.0.0.1:{self.hub.port}")

    def send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def project_for(self, query):
        """The project asked for, else the one with the most recent session activity, else the last found."""
        wanted = urllib.parse.parse_qs(query).get("project", [""])[0]
        projects = self.hub.project_list()
        match = [p for p in projects if str(p) == wanted]
        if match or not projects:
            return match[0] if match else None

        def activity(p):
            try:
                return max(f.stat().st_mtime for f in (p / ".claude" / "sessions").glob("*.md"))
            except (OSError, ValueError):
                return 0
        return max(reversed(projects), key=activity)

    def do_GET(self):
        if not self.allowed_host():
            return self.send(403, dict(error="unknown host"))
        url = urllib.parse.urlsplit(self.path)
        if url.path in PAGES:
            page = PAGES[url.path].read_text().replace("/*THEME_CSS*/", THEME_CSS).replace("/*MD_CSS*/", MD_CSS)
            return self.send(200, page, "text/html")
        if url.path == "/api/ping":
            return self.send(200, dict(ok=True, pid=os.getpid(), version=plugin_version(),
                                       projects=[str(p) for p in self.hub.projects],
                                       found=[str(p) for p in self.hub.project_list()]))
        if url.path == "/api/data":
            project = self.project_for(url.query)
            return self.send(200, data.build(project, self.hub.content, self.hub.project_list()))
        if url.path == "/api/events":
            return self.stream()
        if url.path == "/api/reviews":
            listed = reviews.list_reviews(self.hub.project_list())
            for review in listed:
                runner = self.hub.sessions.get((review["project"], review["id"]))
                review["running"] = bool(runner and runner.running())
            return self.send(200, dict(reviews=listed))
        if url.path in ("/api/review", "/api/review/diff", "/api/review/references"):
            query = {key: values[0] for key, values in urllib.parse.parse_qs(url.query).items()}
            return self.review_request(query, url.path)
        return self.send(404, dict(error="not found"))

    def review_request(self, body, path):
        """Every review endpoint: the project must be on the dashboard; a refused change answers 409 with why."""
        wanted = pathlib.Path(body.get("project") or "").expanduser().resolve()
        project = next((p for p in self.hub.project_list() if p.resolve() == wanted), None)
        if project is None:
            return self.send(404, dict(error=f"not on the dashboard: {wanted}"))
        review_id = str(body.get("id", ""))
        try:
            if path == "/api/review/start":
                review_id = reviews.review_id_for(body.get("source"))
                if (reviews.reviews_root(project) / review_id / "review.json").exists():
                    raise review_state.Refused(f"{review_id} is in progress; resume it instead")
                self.hub.session(project, review_id).start(body["source"])
                return self.send(200, dict(ok=True, id=review_id))
            if path == "/api/review/stop":
                if not reviews.ID.match(review_id):
                    raise review_state.Refused(f"not a review id: {review_id!r}")
                self.hub.session(project, review_id).stop()
                return self.send(200, dict(ok=True))
            reviews.review_dir(project, review_id)
            runner = self.hub.session(project, review_id)
            if path == "/api/review":
                return self.send(200, dict(reviews.read_review(project, review_id), running=runner.running()))
            if path == "/api/review/resume":
                if not runner.running():
                    runner.resume()
                return self.send(200, dict(ok=True))
            if path == "/api/review/diff":
                return self.send(200, reviews.diff_text(project, review_id, body.get("path")), "text/plain")
            if path == "/api/review/references":
                return self.send(200, dict(references=reviews.references(project, review_id, body.get("path", ""))))
            if path == "/api/review/send":
                return self.send(200, send_review.send(reviews.review_dir(project, review_id)))
            if path == "/api/review/change":
                reviews.developer_change(project, review_id, body.get("action"), body)
                runner.deliver()
                return self.send(200, dict(ok=True))
            if path == "/api/review/message":
                message = {key: value for key, value in body.items() if key not in ("project", "id")}
                message_id = reviews.add_message(project, review_id, message)
                runner.deliver()
                return self.send(200, dict(ok=True, id=message_id))
        except review_state.Refused as refusal:
            return self.send(409, dict(error=str(refusal)))
        return self.send(404, dict(error="not found"))

    def stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        hub = self.hub
        with hub.lock:
            hub.clients += 1
            seen = hub.version
        try:
            self.wfile.write(b"event: hello\ndata: {}\n\n")
            self.wfile.flush()
            while True:
                with hub.lock:
                    hub.lock.wait_for(lambda: hub.version != seen, timeout=15)
                    fresh, changed, seen = hub.version != seen, list(hub.changed), hub.version
                message = f"event: change\ndata: {json.dumps(changed)}\n\n" if fresh else ": keep-alive\n\n"
                self.wfile.write(message.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with hub.lock:
                hub.clients -= 1
                hub.last_client = time.time()

    def do_POST(self):
        if not self.allowed_host() or self.headers.get("X-Craftsman") != "1":
            return self.send(403, dict(error="refused: not from the dashboard page"))
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send(400, dict(error="bad json"))
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/api/projects":
            project = pathlib.Path(body.get("path", "")).expanduser().resolve()
            if not project.is_dir():
                return self.send(400, dict(error=f"not a directory: {project}"))
            self.hub.add_project(project)
            return self.send(200, dict(ok=True, projects=[str(p) for p in self.hub.project_list()]))
        if url.path == "/api/projects/remove":
            project = pathlib.Path(body.get("path", "")).expanduser().resolve()
            if not self.hub.remove_project(project):
                return self.send(404, dict(error=f"not on the dashboard: {project}"))
            return self.send(200, dict(ok=True, projects=[str(p) for p in self.hub.project_list()]))
        if url.path.startswith("/api/review/"):
            return self.review_request(body, url.path)
        if url.path == "/api/toggle":
            action, entry_id = body.get("action"), str(body.get("id", ""))
            if action not in ("enable", "disable") or not entry_id:
                return self.send(400, dict(error="need action enable|disable and an id"))
            cmd = [sys.executable, str(HERE / "set_enabled.py"), str(self.hub.content), action, entry_id, "--json"]
            if body.get("yes"):
                cmd.append("--yes")
            result = subprocess.run(cmd, capture_output=True, text=True)
            try:
                out = json.loads(result.stdout)
            except ValueError:
                out = dict(ok=False, error=(result.stdout + result.stderr).strip() or "set_enabled.py failed")
            return self.send({0: 200, 3: 409}.get(result.returncode, 400), out)
        return self.send(404, dict(error="not found"))


def serve(content, projects, port):
    server = None
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit(f"no free port in {port}..{port + 9}")
    server.daemon_threads = True
    hub = Hub(content, projects, server.server_address[1])
    Handler.hub = hub
    hub.save()

    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=hub.watch, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        hub.stop_sessions()
        state = read_state()
        if state and state.get("pid") == os.getpid():
            STATE.unlink(missing_ok=True)


# ---- start / stop / status -------------------------------------------------------------------------------------

def read_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def request(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Host": f"127.0.0.1:{port}", "X-Craftsman": "1",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read())


def running():
    state = read_state()
    if not state:
        return None
    try:
        ping = request(state["port"], "/api/ping")
    except (OSError, ValueError):
        return None
    return state if ping.get("pid") == state.get("pid") else None


def stop_server(state):
    try:
        os.kill(state["pid"], signal.SIGTERM)
    except OSError:
        pass
    for _ in range(30):
        if running() is None:
            break
        time.sleep(0.1)
    STATE.unlink(missing_ok=True)


def start(project, content, port):
    state = running()
    if state and state.get("version") == plugin_version() and state.get("content") == str(content):
        request(state["port"], "/api/projects", dict(path=str(project)))
        print(f"craftsman dashboard: http://localhost:{state['port']}")
        print(f"(already running -- {project} added)")
        return
    projects = [project]
    if state:
        projects = [pathlib.Path(p) for p in state.get("projects", [])] + [project]
        stop_server(state)
        print(f"replaced a dashboard server from plugin {state.get('version')} with {plugin_version()}")
    cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), "serve", "--content", str(content),
           "--port", str(port)] + [arg for p in dict.fromkeys(projects) for arg in ("--project", str(p))]
    with open(LOG, "a") as log:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        time.sleep(0.1)
        state = running()
        if state:
            print(f"craftsman dashboard: http://localhost:{state['port']}")
            return
    sys.exit(f"the dashboard server did not come up -- see {LOG}")


def start_review(port, project, source):
    """Start the review of `source` on the running server, or resume it when it is in progress; returns its URL."""
    review_id = reviews.review_id_for(source)
    try:
        request(port, "/api/review/start", dict(project=str(project), source=source))
    except urllib.error.HTTPError as refusal:
        if refusal.code != 409:
            raise
        request(port, "/api/review/resume", dict(project=str(project), id=review_id))
    return f"http://localhost:{port}/review?project={project}&review={review_id}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["on", "off", "start", "stop", "status", "remove", "serve", "review"])
    ap.add_argument("--source", help="for `review`: a pull request URL, or <target>:<source>")
    ap.add_argument("--project", action="append", default=[])
    ap.add_argument("--content", default=str(pathlib.Path.home() / ".claude" / "craftsman"))
    ap.add_argument("--port", type=int, default=4747)
    args = ap.parse_args()
    args.command = {"on": "start", "off": "stop"}.get(args.command, args.command)
    content = pathlib.Path(args.content).expanduser().resolve()
    projects = [pathlib.Path(p).expanduser().resolve() for p in args.project] or [pathlib.Path.cwd()]

    if args.command == "serve":
        return serve(content, projects, args.port)
    if args.command == "start":
        return start(projects[-1], content, args.port)
    if args.command == "review":
        start(projects[-1], content, args.port)
        try:
            print(f"review: {start_review(running()['port'], projects[-1], args.source)}")
        except (review_state.Refused, urllib.error.HTTPError) as refusal:
            sys.exit(f"the review did not start: {getattr(refusal, 'reason', refusal)}")
        return
    state = running()
    if args.command == "remove":
        if not state:
            print("no dashboard server running")
            return
        project = projects[-1]
        try:
            out = request(state["port"], "/api/projects/remove", dict(path=str(project)))
        except urllib.error.HTTPError:
            print(f"{project} is not on the dashboard")
            return
        print(f"removed {project} from the dashboard -- its files are untouched")
        if not out["projects"]:
            print("no project left; the server keeps running until `off`")
        return
    if args.command == "stop":
        if not state:
            print("no dashboard server running")
            STATE.unlink(missing_ok=True)
            return
        stop_server(state)
        print(f"stopped the dashboard server on port {state['port']}")
        return
    if not state:
        print("no dashboard server running")
        return
    print(f"craftsman dashboard: http://localhost:{state['port']}  (plugin {state['version']}, pid {state['pid']})")
    ping = request(state["port"], "/api/ping")
    for root in ping.get("projects", []):
        print(f"  started from: {root}")
        inside = [p for p in ping.get("found", []) if p != root and p.startswith(root.rstrip("/") + "/")]
        for p in inside:
            print(f"    project: {p[len(root.rstrip('/')) + 1:]}")


if __name__ == "__main__":
    main()
