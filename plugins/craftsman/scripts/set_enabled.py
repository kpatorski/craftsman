#!/usr/bin/env python3
"""Enable or disable a directive, protocol, or bundle by id -- the whole of MANAGEMENT.md, "Enable / disable", as one
script: resolving the id, the bundle cascade, `requires` resolution in both directions, the row moves (through
`toggle_table_row.py`), and the commit. `/craftsman:enable` / `/craftsman:disable` and the dashboard's switches both
call this, so the two can never disagree about what a toggle does.

Usage:
    set_enabled.py <content-root> enable|disable <id> [--yes] [--json] [--no-commit]

Without `--yes`, a toggle that would also change *other* bundles stops before writing anything and reports them:
enabling a bundle whose `requires` are installed but disabled, or disabling a bundle another enabled bundle
requires. Re-run with `--yes` once the developer has agreed. A required bundle that is not installed at all always
stops, `--yes` or not -- there is nothing to enable. Toggling an entry into the table it is already in is a no-op.

Exit codes: 0 done (or nothing to do), 2 the id is unknown or a requirement is not installed, 3 confirmation needed.
`--json` prints one object instead of prose: {"ok", "changed", "confirm", "error", "commit"}.
"""
import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_dashboard import collect_entries  # noqa: E402

TOGGLE = pathlib.Path(__file__).resolve().parent / "toggle_table_row.py"


def index_file(root, entry):
    if entry["kind"] == "bundle":
        return root / "bundles" / "index.md"
    if entry["bundle"]:
        return root / "bundles" / entry["bundle"] / "bundle.md"
    return root / ("directives" if entry["kind"] == "directive" else "protocols") / "index.md"


def plan(entries, target, enable):
    """(moves, extra_bundles, missing): the ids to move in order, the other bundles pulled in, uninstalled requires."""
    by_id = {e["id"]: e for e in entries}
    bundles = {e["id"]: e for e in entries if e["kind"] == "bundle"}
    extra, missing, order = [], [], []

    if target["kind"] == "bundle":
        if enable:
            def pull(bundle_id, seen):
                for req in bundles[bundle_id]["requires"]:
                    if req in seen:
                        continue
                    seen.add(req)
                    if req not in bundles:
                        missing.append(req)
                        continue
                    pull(req, seen)
                    if not bundles[req]["enabled"]:
                        extra.append(req)
                        order.append(req)
            pull(target["id"], {target["id"]})
        else:
            def push(bundle_id, seen):
                for other in bundles.values():
                    if other["id"] in seen or not other["enabled"] or bundle_id not in other["requires"]:
                        continue
                    seen.add(other["id"])
                    push(other["id"], seen)
                    extra.append(other["id"])
                    order.append(other["id"])
            push(target["id"], {target["id"]})
        order.append(target["id"])
        moves = []
        for bundle_id in order:
            moves.append(by_id[bundle_id])
            moves += [e for e in entries if e["bundle"] == bundle_id]
    else:
        moves = [target]
    return moves, extra, missing


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def commit(root, touched, message):
    if git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return None
    rel = [str(p.relative_to(root)) for p in touched]
    if not git(root, "status", "--porcelain", "--", *rel).stdout.strip():
        return None
    git(root, "add", "--", *rel)
    if git(root, "commit", "-q", "-m", message, "--", *rel).returncode != 0:
        return None
    return git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def run(root, action, entry_id, yes, do_commit):
    enable = action == "enable"
    entries = collect_entries(root)
    target = next((e for e in entries if e["id"] == entry_id), None)
    if target is None:
        return 2, dict(ok=False, error=f"'{entry_id}' is not installed -- no directive, protocol or bundle has this id.")

    moves, extra, missing = plan(entries, target, enable)
    if missing:
        return 2, dict(ok=False, error=f"bundle '{entry_id}' requires {', '.join(missing)}, which is not installed. "
                                       f"Install it first; nothing was changed.")
    if extra and not yes:
        why = (f"'{entry_id}' requires {', '.join(extra)}, currently disabled" if enable else
               f"{', '.join(extra)} require{'s' if len(extra) == 1 else ''} '{entry_id}' and would be left broken")
        return 3, dict(ok=False, confirm=dict(bundles=extra, action=action,
                                              message=f"{why}. {action.capitalize()} {'them' if len(extra) > 1 else 'it'} "
                                                      f"too?"))

    changed, touched = [], []
    for e in moves:
        if e["enabled"] == enable:
            continue
        path = index_file(root, e)
        result = subprocess.run([sys.executable, str(TOGGLE), str(path), e["id"], action],
                                capture_output=True, text=True)
        if result.returncode != 0:
            return 2, dict(ok=False, changed=changed, error=(result.stdout + result.stderr).strip())
        changed.append(e["id"])
        if path not in touched:
            touched.append(path)

    sha = None
    if changed and do_commit:
        what = target["kind"] + " " + entry_id + (f" (with {', '.join(extra)})" if extra else "")
        sha = commit(root, touched, f"{action} {what}")
    return 0, dict(ok=True, changed=changed, commit=sha, cascade=target["kind"] == "bundle")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root")
    ap.add_argument("action", choices=["enable", "disable"])
    ap.add_argument("id")
    ap.add_argument("--yes", action="store_true", help="also toggle the other bundles requires resolution names")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()

    code, out = run(pathlib.Path(args.root).expanduser().resolve(), args.action, args.id, args.yes, not args.no_commit)
    if args.json:
        print(json.dumps(out))
    elif code == 3:
        print(out["confirm"]["message"] + " Re-run with --yes to do so; nothing was changed.")
    elif not out["ok"]:
        print(out["error"])
    elif not out["changed"]:
        print(f"{args.id} is already {args.action}d -- no change.")
    else:
        print(f"{args.action}d: {', '.join(out['changed'])}" + (f" (commit {out['commit']})" if out["commit"] else ""))
        if out.get("cascade"):
            print("A bundle toggle moves every member, overwriting any member toggled individually before.")
    sys.exit(code)


if __name__ == "__main__":
    main()
