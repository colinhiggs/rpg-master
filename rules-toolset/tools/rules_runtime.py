# rules_runtime.py — how the game server consumes the compiled rules.
#
# Drop this next to server.py/data.py and point RULES_BUILD_DIR at the
# rules project's build/ directory (or copy build/mechanics.json into
# the server's own folder as a build step).
#
# The point: the server must not carry its own copy of any game
# constant. `data.py` currently hardcodes starting HP of 20, a dice
# regex, a grid size — each of those is a second source of truth that
# can silently disagree with the book. After wiring this in, they all
# come from mechanics.json, which is generated from the same rule files
# the book is generated from. Change the rule, rebuild, and BOTH the
# book and the server behaviour move together.
#
# Fail-fast is deliberate throughout: a missing mechanic should crash at
# startup with a clear message, not silently fall back to a default that
# contradicts the printed rules.

import json
from pathlib import Path

RULES_BUILD_DIR = Path(__file__).parent / "rules_build"
MECHANICS_PATH = RULES_BUILD_DIR / "mechanics.json"
SNIPPETS_PATH = RULES_BUILD_DIR / "snippets.json"

_mechanics = None
_snippets = None


class RulesNotBuilt(Exception):
    pass


def load_mechanics(path: Path = None) -> dict:
    global _mechanics
    path = path or MECHANICS_PATH
    if not path.exists():
        raise RulesNotBuilt(
            f"{path} not found. Run the rules build (tools/build.py) and copy "
            "build/mechanics.json here — the server has no built-in defaults "
            "for game constants by design."
        )
    with open(path, encoding="utf-8") as f:
        _mechanics = json.load(f)["rules"]
    return _mechanics


def load_snippets(path: Path = None) -> dict:
    """Served to the client for context help / tooltips. Not needed for
    game logic — a missing snippets file degrades the UI, it does not
    change what the rules do — so this one returns {} rather than
    raising."""
    global _snippets
    path = path or SNIPPETS_PATH
    if not path.exists():
        _snippets = {}
        return _snippets
    with open(path, encoding="utf-8") as f:
        _snippets = json.load(f)
    return _snippets


def mech(rule_id: str, key: str, default=...):
    """Read one mechanic. `mech('movement', 'base_move_tiles')`.

    Raises by default if missing: a typo'd key should fail loudly at
    startup, not quietly return None and produce a rules-violating game.
    Pass an explicit default only where absence is genuinely meaningful."""
    if _mechanics is None:
        load_mechanics()
    rule = _mechanics.get(rule_id)
    if rule is None:
        if default is not ...:
            return default
        raise KeyError(
            f"no rule '{rule_id}' in mechanics.json "
            f"(have: {', '.join(sorted(_mechanics))})"
        )
    if key not in rule:
        if default is not ...:
            return default
        raise KeyError(
            f"rule '{rule_id}' has no mechanic '{key}' "
            f"(have: {', '.join(sorted(rule))})"
        )
    return rule[key]


def snippet(rule_id: str):
    if _snippets is None:
        load_snippets()
    return _snippets.get(rule_id)


def all_snippets():
    if _snippets is None:
        load_snippets()
    return _snippets


# ---------------------------------------------------------------------
# Convenience accessors for the constants data.py actually needs.
# Defined here rather than scattered through data.py so there is exactly
# one place to look when asking "where does the server get this number?"
# ---------------------------------------------------------------------
def grid_size():
    return int(mech("movement", "grid_size"))


def starting_hp():
    return int(mech("damage-and-healing", "starting_hp"))


def min_hp():
    return int(mech("damage-and-healing", "min_hp"))


def healing_caps_at_max():
    return bool(mech("damage-and-healing", "healing_caps_at_max"))


def dice_notation_pattern():
    return mech("dice-rolls", "notation_pattern")


def default_roll():
    return mech("dice-rolls", "default_roll")


def max_dice_per_roll():
    return int(mech("dice-rolls", "max_dice_per_roll"))


def max_sides():
    return int(mech("dice-rolls", "max_sides"))


def base_move_tiles():
    return int(mech("movement", "base_move_tiles"))


def can_move_through_enemies():
    return bool(mech("movement", "can_move_through_enemies"))
