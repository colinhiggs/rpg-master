# runtime.py - reading a built ruleset back, for something that plays it.
#
# The compiler's job ends at build/: mechanics.json, snippets.json, a
# book. This module is the other end of that pipe, for a consumer that
# has to run the game rather than print it - the server is the first
# one. It is here rather than in the consumer because finding a
# ruleset, reading its stamp and failing usefully on a missing key are
# the same job whatever the game is, and two consumers should not
# invent two answers to it.
#
# What it deliberately does NOT do is name a rule or a mechanic. Doing
# that is knowing a particular game, which SHARING.md forbids here for
# good reason: the only ruleset the toolset can legally name keys from
# is its own fixture, so an accessor layer written at this level binds
# itself to `demo` and looks correct forever. That is exactly what
# happened to the tools/rules_runtime.py this module replaces. The
# layer that names keys belongs to the consumer, which is allowed to
# know which game it is running.
#
# Fail-fast is the other half of the contract, and it is inherited from
# the rest of the pipeline: a missing mechanic raises, and says what it
# looked for and what was there instead. A consumer that quietly
# defaults is a second source of truth for a number the book already
# states, which is the whole thing this pipeline exists to prevent.

import json
from pathlib import Path

from .compile import RuleError
from .lookup import find_ruleset, search_path

MECHANICS_FILE = "mechanics.json"
SNIPPETS_FILE = "snippets.json"
BUILD_DIR = "build"


class RulesNotBuilt(RuleError):
    """A ruleset was found on disk but has not been compiled."""


class Mechanics:
    """One ruleset's compiled values, read back.

    An instance is a ruleset, not a process-wide singleton: a consumer
    that wants two of them - to compare versions, or to serve two
    tables - simply holds two. The module the old runtime used for this
    was global state, which made it untestable and unable to say which
    ruleset an answer came from."""

    def __init__(self, name, directory, rules, version=None, generated=None,
                 snippets=None):
        self.name = name
        self.directory = Path(directory)
        self.rules = rules
        self.version = version
        self.generated = generated
        self._snippets = snippets

    def __repr__(self):
        stamp = self.version or "unversioned"
        return f"<Mechanics {self.name} {stamp} from {self.directory}>"

    # -- values ------------------------------------------------------
    def mech(self, rule_id: str, key: str, default=...):
        """Read one mechanic: `m.mech("movement", "grid_size")`.

        Raises by default. Pass an explicit default only where absence
        is genuinely meaningful - not to paper over a key you hope is
        there, because the error below is the only thing standing
        between a typo and a game that silently contradicts its own
        book."""
        rule = self.rules.get(rule_id)
        if rule is None:
            if default is not ...:
                return default
            raise KeyError(
                f"ruleset '{self.name}' has no rule '{rule_id}' "
                f"(it has: {', '.join(sorted(self.rules))})"
            )
        if key not in rule:
            if default is not ...:
                return default
            raise KeyError(
                f"ruleset '{self.name}' rule '{rule_id}' has no mechanic "
                f"'{key}' (it has: {', '.join(sorted(rule))})"
            )
        return rule[key]

    def has(self, rule_id: str, key: str) -> bool:
        """Whether a mechanic exists, without reading it. For a consumer
        asking what a ruleset can answer rather than demanding it."""
        return key in self.rules.get(rule_id, {})

    # -- prose -------------------------------------------------------
    def snippet(self, rule_id: str):
        """One document's compiled prose, or None.

        Missing snippets degrade a consumer's help text; they cannot
        change what the game does. So this half does not raise, and the
        file is read only when something asks for it."""
        if self._snippets is None:
            self._snippets = _read_snippets(self.directory)
        return self._snippets.get(rule_id)

    def snippet_ids(self):
        if self._snippets is None:
            self._snippets = _read_snippets(self.directory)
        return tuple(sorted(self._snippets))


def _read_snippets(ruleset_dir: Path) -> dict:
    path = Path(ruleset_dir) / BUILD_DIR / SNIPPETS_FILE
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    return {k: v for k, v in loaded.items() if not k.startswith("_")}


def load_ruleset(name: str, path=None) -> Mechanics:
    """Find a built ruleset by name and read its values.

    `path` skips the search for a ruleset that lies somewhere the two
    built-in places and $RULESET_PATH cannot reach, exactly as the
    build and test tools' --path does."""
    if path is not None:
        directory = Path(path)
        if not directory.exists():
            raise RuleError(f"no ruleset at {directory}")
    else:
        directory, _where = find_ruleset(name)
        if directory is None:
            looked = ", ".join(str(root) for root, _ in search_path())
            raise RuleError(
                f"no ruleset named '{name}'. Looked in: {looked}. "
                f"Set $RULESET_PATH, or pass an explicit path."
            )

    mechanics_path = directory / BUILD_DIR / MECHANICS_FILE
    if not mechanics_path.exists():
        raise RulesNotBuilt(
            f"{mechanics_path} does not exist. Ruleset '{name}' is on disk "
            f"but has not been compiled - run tools/build.py {name}. There "
            "are no built-in defaults for game values by design."
        )
    with open(mechanics_path, encoding="utf-8") as f:
        loaded = json.load(f)
    if "rules" not in loaded:
        raise RulesNotBuilt(
            f"{mechanics_path} has no 'rules' block, so it is not a "
            "mechanics file this toolset produced."
        )
    return Mechanics(
        name=name,
        directory=directory,
        rules=loaded["rules"],
        version=loaded.get("_version"),
        generated=loaded.get("_generated"),
    )
