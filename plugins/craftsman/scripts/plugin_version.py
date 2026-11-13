"""Which version of this plugin last touched the installed content, compared with the running one -- see MANAGEMENT.md,
"Plugin version".

    plugin_version.py [<content dir>]     default: ~/.claude/craftsman

Prints the one line to say to the developer, or nothing when there is nothing to say. An older or missing marker is
moved to the running version; a newer one is kept, because another session already runs that version.
"""
import json
import pathlib
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
MARKER = ".craftsman-plugin-version"


def running():
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


def as_tuple(version):
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return ()


def check(content, version):
    """What to say about the marker of `content`, or None; the marker is written when it is older or missing."""
    content = pathlib.Path(content)
    if not content.is_dir():
        return None
    marker = content / MARKER
    recorded = marker.read_text().strip() if marker.is_file() else ""
    if recorded == version:
        return None
    if recorded and as_tuple(recorded) > as_tuple(version):
        return (f"Another session runs craftsman {recorded}, newer than this session's {version}; "
                f"a fresh session picks it up.")
    marker.write_text(version + "\n")
    return (f"craftsman updated since the content was last touched ({recorded or 'unknown'} → {version}); "
            "see craftsman's CHANGELOG.md.")


def main(argv):
    content = argv[1] if len(argv) > 1 else pathlib.Path.home() / ".claude" / "craftsman"
    said = check(content, running())
    if said:
        print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
