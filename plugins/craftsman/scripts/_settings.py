"""The developer's craftsman settings: `<craftsman home>/settings.json`, one JSON object. Keys:

- `theme`: the colour palette of every craftsman page (see _theme.py);
- `review-tools`: tools a review's headless session may use besides its fixed list, as permission rules -- for
  example `mcp__jira` for every tool of the MCP server `jira` (see REVIEW.md, "The review's session");
- `review-directives`: the developer's default set of directives for every review, `{<directive id>: true | false}`,
  where it differs from the workshop (see REVIEW.md, "Directives");
- `send-fix-prompt`: whether Send also posts the fix prompt at first, true unless set (see REVIEW.md, "Fix prompts");
- `comment-style`: the default shape of a comment the AI Agent writes of a draft, some of `review_state.COMMENT_STYLE`
  (see REVIEW.md, "Drafts");
- `models`: the model of each tier, `{"fast" | "balanced" | "deep": <model>}`, where it differs from the default (see
  model_tiers.py and EXECUTION.md, "Choosing a model");
- `dictation-model`: the dictation engine's active model, set by `dictation.py` (see REVIEW.md, "Dictation");
- `dictation-server`: an external speech server, {"url", "token"}, used instead of the built-in engine."""
import json

import _reviews
import review_state


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


def send_fix_prompt():
    """Whether Send's "Also post a fix prompt" starts ticked."""
    return read().get("send-fix-prompt") is not False


def set_send_fix_prompt(on):
    update("send-fix-prompt", bool(on))
    return send_fix_prompt()


def comment_style():
    """The default shape of a comment the AI Agent writes of a draft: the developer's, part by part, else the
    plugin's."""
    kept = read().get("comment-style")
    kept = kept if isinstance(kept, dict) else {}
    return {key: kept[key] if review_state.known_style(key, kept.get(key)) else default
            for key, default in review_state.COMMENT_STYLE_DEFAULT.items()}


def set_comment_style(style):
    """Change some parts of the default shape; a part not known is refused, and nothing changes."""
    update("comment-style", dict(comment_style(), **review_state.check_comment_style(style)))
    return comment_style()
