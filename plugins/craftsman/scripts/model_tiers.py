#!/usr/bin/env python3
"""The model tiers -- see EXECUTION.md, "Choosing a model". craftsman names the work a model does by tier, never by
model: `fast`, `balanced` or `deep`. Which model each tier is lives in the craftsman settings (`models`, a tier ->
model object) and is set from the dashboard's Manage view; a tier the developer has not set is the default below, the
one place in craftsman that names models.

Run on its own, it prints the mapping on one line: `fast = haiku, balanced = sonnet, deep = opus`.
"""
import json
import os
import pathlib
import re

TIERS = {
    "fast": "Mechanical work with nothing to weigh: list, copy, check against a rule already written down.",
    "balanced": "Steps a stronger model already laid out: follow the plan, apply the given rules, report.",
    "deep": "Analysis nobody has done yet: understand the change, weigh trade-offs, decide what matters.",
}
DEFAULTS = {"fast": "haiku", "balanced": "sonnet", "deep": "opus"}
# the model names Claude Code's Agent tool takes; offered when the developer has no lineup of their own
ALIASES = ("haiku", "sonnet", "opus", "fable")
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]*")


def _settings_file():
    home = os.environ.get("CRAFTSMAN_HOME") or pathlib.Path.home() / ".craftsman"
    return pathlib.Path(home) / "settings.json"


def _chosen():
    try:
        chosen = json.loads(_settings_file().read_text()).get("models")
    except (OSError, ValueError, AttributeError):
        return {}
    return chosen if isinstance(chosen, dict) else {}


def models():
    """Each tier's model: the developer's where it is a usable name, else the default."""
    chosen = _chosen()
    return {tier: chosen[tier].strip() if isinstance(chosen.get(tier), str) and chosen[tier].strip() else default
            for tier, default in DEFAULTS.items()}


def model(tier):
    return models()[tier]


def set_model(tier, name):
    """Map a tier to a model; an empty name brings the default back. Anything else not a model name is refused."""
    if tier not in TIERS:
        raise ValueError(f"no tier {tier!r}: the tiers are {', '.join(TIERS)}")
    if not isinstance(name, str):
        raise ValueError("a model name is text")
    name = name.strip()
    if name and not MODEL_NAME.fullmatch(name):
        raise ValueError(f"not a model name: {name!r}")
    import _settings  # the server's settings writer, kept out of the hooks that import this module
    chosen = dict(_chosen())
    if name:
        chosen[tier] = name
    else:
        chosen.pop(tier, None)
    _settings.update("models", chosen)
    return models()


def tier_of(name):
    """The tier a model is mapped to, or None. An alias belongs to a tier mapped to a full id with it in the name --
    a subagent can be started on an alias only."""
    mapped = models()
    for tier, model_name in mapped.items():
        if name == model_name:
            return tier
    for tier, model_name in mapped.items():
        if name in ALIASES and name in model_name:
            return tier
    return None


def described():
    return ", ".join(f"{tier} = {name}" for tier, name in models().items())


def suggestions():
    """The models to offer for a tier: the lineup the developer set for Claude Code (`availableModels`), if any,
    else the names the Agent tool takes."""
    config = os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude"
    try:
        lineup = json.loads((pathlib.Path(config) / "settings.json").read_text()).get("availableModels")
    except (OSError, ValueError, AttributeError):
        lineup = None
    if isinstance(lineup, list) and all(isinstance(name, str) for name in lineup) and lineup:
        return lineup
    return list(ALIASES)


def listing():
    """What the dashboard's Manage view shows."""
    mapped = models()
    return dict(tiers=[dict(id=tier, says=says, model=mapped[tier], default=DEFAULTS[tier])
                       for tier, says in TIERS.items()], suggestions=suggestions())


if __name__ == "__main__":
    print(described())
