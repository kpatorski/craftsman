"""The developer's craftsman settings: `<craftsman home>/settings.json`, one JSON object. Keys:

- `theme`: the colour palette of every craftsman page (see _theme.py);
- `review-tools`: tools a review's headless session may use besides its fixed list, as permission rules -- for
  example `mcp__jira` for every tool of the MCP server `jira` (see REVIEW.md, "The review's session");
- `review-directives`: the developer's default set of directives for every review, `{<directive id>: true | false}`,
  where it differs from the workshop (see REVIEW.md, "Directives")."""
import json

import _reviews


def settings_file():
    return _reviews.home() / "settings.json"


def read():
    """The settings; empty when the file is missing or not JSON."""
    try:
        settings = json.loads(settings_file().read_text())
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def update(key, value):
    """Set one key and keep the others."""
    settings = read()
    settings[key] = value
    settings_file().parent.mkdir(parents=True, exist_ok=True)
    settings_file().write_text(json.dumps(settings, indent=2) + "\n")


def review_tools():
    """The tools the developer lets every review's session use besides its fixed list."""
    return [str(tool) for tool in read().get("review-tools") or [] if str(tool).strip()]


def allow_review_tool(rule, allowed):
    """Add a tool to `review-tools`, or take it back."""
    tools = [tool for tool in review_tools() if tool != rule]
    update("review-tools", tools + [rule] if allowed else tools)


def review_directives():
    """The directives the developer switched on or off for every review, where it differs from the workshop."""
    chosen = read().get("review-directives")
    if not isinstance(chosen, dict):
        return {}
    return {str(key): value for key, value in chosen.items() if isinstance(value, bool)}
