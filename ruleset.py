# ruleset.py - which game this server is running, and where each of its
# numbers comes from.
#
# The toolset deliberately cannot contain this file. Naming a rule id
# and a mechanic key is knowing a particular game, and SHARING.md's
# central rule is that nothing in rules-toolset/ may know one. The
# accessor layer that used to live there (tools/rules_runtime.py) got
# around that by naming keys from `demo`, the toolset's own fixture -
# and `demo` was itself written to describe data.py's constants, so the
# loop closed on itself and proved nothing. Every one of its accessors
# resolved against demo and none against a real ruleset.
#
# So the naming happens here, in the server, which is allowed to know
# which game it is running. The shape is:
#
#   NEEDS      what the server needs a number for, in its own words.
#   BINDINGS   per ruleset, which mechanic answers each need.
#
# A need a ruleset does not answer is one of two things, and the
# difference is the whole point of splitting them:
#
#   - TABLE-owned. The book has no opinion because it is not a rules
#     question - how wide the battle map is, how many dice one click
#     may roll. The server supplies its own, and says so at startup.
#   - RULES-owned. The book must answer it, and if it cannot, this
#     server cannot honestly run that ruleset yet. It refuses to start
#     and names what is missing.
#
# That second list is not a failure of this file. It is the shape of
# what a ruleset would have to gain - or what the server's state would
# have to grow - before it can be played here, generated rather than
# guessed at. For `ico` today it comes to two needs, and both are the
# same underlying fact: a token has one hit point pool and Ico has two.

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "rules-toolset"))

from rulesc.runtime import RulesNotBuilt, load_ruleset  # noqa: E402

# Which ruleset to play. `demo` by default because it is the one that
# ships inside this repository and the one the server has always in
# fact been implementing.
RULESET_ENV = "RPG_RULESET"
DEFAULT_RULESET = "demo"

TABLE = "table"    # the server may answer this itself
RULES = "rules"    # the book must answer it or we do not start


class Need:
    """One number the server needs, in the server's vocabulary."""

    def __init__(self, name, owner, why, fallback=None):
        self.name = name
        self.owner = owner
        self.why = why
        self.fallback = fallback


NEEDS = (
    Need("default_roll", RULES,
         "what a bare roll means when nobody types a notation"),
    Need("min_hp", RULES,
         "the floor a token's hit points clamp to"),
    Need("starting_hp", RULES,
         "what a freshly joined player's token has"),
    Need("healing_caps_at_max", RULES,
         "whether healing may take a token above its maximum"),
    Need("grid_size", TABLE,
         "how many squares wide the battle map is", fallback=14),
    Need("dice_notation", TABLE,
         "the syntax the free-form roller accepts",
         fallback=r"^(\d*)d(\d+)([+-]\d+)?$"),
    Need("max_dice_per_roll", TABLE,
         "a sanity limit on one roll, so a client cannot ask for a "
         "million dice", fallback=100),
    Need("max_sides", TABLE,
         "the same, for die size", fallback=1000),
)

NEEDS_BY_NAME = {need.name: need for need in NEEDS}


# Which mechanic answers each need, per ruleset. A need absent from a
# ruleset's map is one that ruleset does not answer; see the module
# docstring for what happens then.
BINDINGS = {
    # demo states all eight, which is unsurprising: it was written to
    # describe this server. It is kept as the default so that the
    # wiring can be exercised end to end against a ruleset that
    # genuinely answers everything.
    "demo": {
        "default_roll": ("dice-rolls", "default_roll"),
        "min_hp": ("damage-and-healing", "min_hp"),
        "starting_hp": ("damage-and-healing", "starting_hp"),
        "healing_caps_at_max": ("damage-and-healing", "healing_caps_at_max"),
        "grid_size": ("movement", "grid_size"),
        "dice_notation": ("dice-rolls", "notation_pattern"),
        "max_dice_per_roll": ("dice-rolls", "max_dice_per_roll"),
        "max_sides": ("dice-rolls", "max_sides"),
    },
    # ico answers the two that are genuinely rules questions about a
    # single number, and cannot answer the two that assume one hit
    # point pool:
    #
    #   starting_hp          core hit points equal constitution, and a
    #                        character also starts with free mastery hit
    #                        points. Both need an attribute and a second
    #                        pool, neither of which a token has.
    #   healing_caps_at_max  recovery is stated as fractions of a
    #                        maximum, which implies the cap without
    #                        stating it, and the two pools refill by
    #                        different routes anyway.
    #
    # The three table-owned ones it is simply silent on, correctly: a
    # battle map's width is not a rule of Ico.
    "ico": {
        "default_roll": ("core-resolution", "standard_die"),
        "min_hp": ("dying", "deaths_door_at_core"),
    },
}


class RulesetUnplayable(Exception):
    """The chosen ruleset does not answer something the server must know."""


class Ruleset:
    """The bound ruleset: every need resolved to a value, with its
    provenance kept so that startup can say where each number came
    from."""

    def __init__(self, mechanics, values, sources, unanswered):
        self.mechanics = mechanics
        self.name = mechanics.name
        self.version = mechanics.version
        self.values = values
        self.sources = sources
        self.unanswered = unanswered

    def __getattr__(self, item):
        try:
            return self.__dict__["values"][item]
        except KeyError:
            raise AttributeError(
                f"'{item}' is not a need this server declares "
                f"(it declares: {', '.join(sorted(NEEDS_BY_NAME))})"
            ) from None

    def provenance(self):
        """One line per need, for the startup log. The point of printing
        it is that a number coming from the table rather than the book
        should be visible rather than assumed."""
        stamp = self.version or "unversioned"
        lines = [f"ruleset '{self.name}' {stamp} from {self.mechanics.directory}"]
        for need in NEEDS:
            lines.append(
                f"  {need.name:<20} {self.values[need.name]!r:<28} "
                f"{self.sources[need.name]}"
            )
        return "\n".join(lines)


def bind(name=None, path=None) -> Ruleset:
    """Load a ruleset and resolve every need against it.

    Raises rather than defaulting when a rules-owned need goes
    unanswered: a server that invented its own starting hit points
    would be a second source of truth for a number the book states,
    which is the thing this whole pipeline exists to prevent."""
    name = name or os.environ.get(RULESET_ENV) or DEFAULT_RULESET
    mechanics = load_ruleset(name, path=path)
    binding = BINDINGS.get(name)
    if binding is None:
        raise RulesetUnplayable(
            f"ruleset '{name}' is built, but this server has no binding for "
            f"it - nothing says which of its mechanics answers which of the "
            f"server's needs. Bindings exist for: "
            f"{', '.join(sorted(BINDINGS))}. Add one to BINDINGS in "
            f"{Path(__file__).name}."
        )

    values, sources, unanswered = {}, {}, []
    for need in NEEDS:
        where = binding.get(need.name)
        if where is not None:
            rule_id, key = where
            if mechanics.has(rule_id, key):
                values[need.name] = mechanics.mech(rule_id, key)
                sources[need.name] = f"{name}:{rule_id}.{key}"
                continue
            # A binding naming a mechanic the ruleset has not got is a
            # stale binding, and is worth saying differently from one
            # that never claimed to answer.
            raise RulesetUnplayable(
                f"the '{name}' binding says {need.name} comes from "
                f"{rule_id}.{key}, and that ruleset has no such mechanic. "
                f"The binding in {Path(__file__).name} is out of date with "
                f"the ruleset it names."
            )
        if need.owner is TABLE:
            values[need.name] = need.fallback
            sources[need.name] = "this server (the book is silent, and this "\
                                 "is not a rules question)"
            continue
        unanswered.append(need)

    if unanswered:
        detail = "\n".join(
            f"  {need.name} - {need.why}" for need in unanswered
        )
        raise RulesetUnplayable(
            f"ruleset '{name}' does not answer "
            f"{len(unanswered)} thing(s) this server must know:\n{detail}\n"
            "These are rules questions, so the server will not invent them. "
            "See the rules-engine entry in TODO.md."
        )
    return Ruleset(mechanics, values, sources, unanswered)
