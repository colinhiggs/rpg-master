# ruleset.py - which game this server is running, and what a creature in
# it has.
#
# The toolset deliberately cannot contain this file. Naming a rule id
# and a mechanic key is knowing a particular game, and SHARING.md's
# central rule is that nothing in rules-toolset/ may know one. The
# accessor layer that used to live there got around that by naming keys
# from `demo`, the toolset's own fixture - and `demo` was itself written
# to describe data.py's constants, so the loop closed on itself and
# proved nothing. See DONE.md for the whole of that.
#
# So the naming happens here, in the server, which is allowed to know
# which game it is running. There are two things to declare:
#
#   NEEDS      single values the server needs, in its own words.
#   BINDINGS   per ruleset: which mechanic answers each need, and what
#              pools a creature in that game has.
#
# A need a ruleset does not answer is one of two things, and the
# difference is the whole point of splitting them:
#
#   - TABLE-owned. The book has no opinion because it is not a rules
#     question - how wide the battle map is, how many dice one click
#     may roll. The server supplies its own, and says so at startup.
#   - RULES-owned. The book must answer it, and if it cannot, this
#     server cannot honestly run that ruleset. It refuses to start and
#     names what is missing.

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "rules-toolset"))

from rulesc.runtime import RulesNotBuilt, load_ruleset  # noqa: E402

RULESET_ENV = "RPG_RULESET"
DEFAULT_RULESET = "demo"

TABLE = "table"    # the server may answer this itself
RULES = "rules"    # the book must answer it or we do not start


class From:
    """A value that comes out of the ruleset rather than out of this
    file. Anything not wrapped in one of these is a literal, and a
    literal in a binding is the server making a reading of its own -
    which is allowed, but should be commented where it happens."""

    def __init__(self, rule_id, key):
        self.rule_id = rule_id
        self.key = key

    def __repr__(self):
        return f"From({self.rule_id}.{self.key})"


class Need:
    """One single value the server needs, in the server's vocabulary."""

    def __init__(self, name, owner, why, fallback=None):
        self.name = name
        self.owner = owner
        self.why = why
        self.fallback = fallback


NEEDS = (
    Need("default_roll", RULES,
         "what a bare roll means when nobody types a notation"),
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


class Pool:
    """One of the tracks a creature's condition is kept on.

    A game with one hit point total declares one of these. Ico declares
    four, and the reason the server had to grow them is that `hp` and
    `maxHp` could not be made to mean two things at once.

    starts       the maximum a freshly made token gets. None means the
                 ruleset does not state one, because it depends on the
                 character - the table supplies it per token, which is
                 what a virtual tabletop is for.
    floor        the value the pool clamps at from below. None means it
                 does not clamp: Ico's core hit points keep going down
                 past zero, and how far is a function of an attribute
                 this server does not hold.
    caps_at_max  whether the current value may exceed the maximum.
    down_at      set on exactly one pool per ruleset: at or below this,
                 the creature is out of the fight. It is not always the
                 same as `floor` - in Ico the floor is open and this is
                 death's door."""

    def __init__(self, name, label, starts=None, floor=None,
                 caps_at_max=True, down_at=None):
        self.name = name
        self.label = label
        self.starts = starts
        self.floor = floor
        self.caps_at_max = caps_at_max
        self.down_at = down_at


BINDINGS = {
    # demo states every single value, which is unsurprising: it was
    # written to describe this server before any of this existed. One
    # pool, and the three properties of it all come out of the book.
    "demo": {
        "scalars": {
            "default_roll": ("dice-rolls", "default_roll"),
            "grid_size": ("movement", "grid_size"),
            "dice_notation": ("dice-rolls", "notation_pattern"),
            "max_dice_per_roll": ("dice-rolls", "max_dice_per_roll"),
            "max_sides": ("dice-rolls", "max_sides"),
        },
        "pools": (
            Pool("hp", "Hit points",
                 starts=From("damage-and-healing", "starting_hp"),
                 floor=From("damage-and-healing", "min_hp"),
                 caps_at_max=From("damage-and-healing", "healing_caps_at_max"),
                 down_at=From("damage-and-healing", "downed_at_hp")),
        ),
        "damage_order": ("hp",),
    },
    # ico answers the one scalar that is a rules question about a single
    # number, and is correctly silent on the four that are the table's.
    # Its pools are where the interesting part is:
    #
    #   mastery/core   two hit point tracks. Damage takes mastery first,
    #                  and the ORDER comes out of the book rather than
    #                  out of this file - see damage_order below.
    #   stamina/spirit the two power sources, which powers are paid for
    #                  out of. They are conditions of a creature in
    #                  exactly the way hit points are, so they are pools.
    #
    # None of the four states a starting maximum, because all four
    # derive from a character: core hit points equal constitution,
    # stamina is based on constitution and spirit on will, and mastery
    # is bought. A token has no attributes, so the table supplies these
    # per token - which is honest for a virtual tabletop, and is the
    # line where rung 1 stops and rung 2 begins.
    #
    # core's floor is deliberately open. `dying.deaths_door_at_core` is
    # 0 and that is where a character goes down, but they keep going
    # down from there and die at negative constitution, so clamping
    # core at zero would be the server inventing a rule Ico does not
    # have. down_at carries the threshold; floor stays None.
    #
    # caps_at_max is a literal True on all four, and that is this file
    # making a reading rather than reporting one: Ico states recovery as
    # fractions of a maximum and a night restoring all of a pool, which
    # only means anything if the maximum is a ceiling. It is not stated
    # as a boolean anywhere, so it is written here where it can be seen
    # rather than bound to a key that does not exist.
    "ico": {
        "scalars": {
            "default_roll": ("core-resolution", "standard_die"),
        },
        "pools": (
            Pool("mastery", "Mastery", floor=0),
            Pool("core", "Core", floor=None,
                 down_at=From("dying", "deaths_door_at_core")),
            Pool("stamina", "Stamina", floor=0),
            Pool("spirit", "Spirit", floor=0),
        ),
        "damage_order": From("hit-points", "damage_order"),
    },
}


class RulesetUnplayable(Exception):
    """The chosen ruleset does not answer something the server must know."""


class BoundPool:
    """A Pool with everything resolved against the ruleset."""

    def __init__(self, name, label, starts, floor, caps_at_max, down_at):
        self.name = name
        self.label = label
        self.starts = starts
        self.floor = floor
        self.caps_at_max = caps_at_max
        self.down_at = down_at

    @property
    def supplied_by_table(self):
        return self.starts is None

    def as_json(self):
        """What the client needs to draw and edit this pool."""
        return {
            "name": self.name,
            "label": self.label,
            "starts": self.starts,
            "floor": self.floor,
            "capsAtMax": self.caps_at_max,
            "downAt": self.down_at,
        }

    def clamp(self, value, maximum):
        if self.caps_at_max and value > maximum:
            value = maximum
        if self.floor is not None and value < self.floor:
            value = self.floor
        return value


class Ruleset:
    """The bound ruleset: every need and every pool resolved, with the
    provenance kept so that startup can say where each came from."""

    def __init__(self, mechanics, values, sources, pools, damage_order):
        self.mechanics = mechanics
        self.name = mechanics.name
        self.version = mechanics.version
        self.values = values
        self.sources = sources
        self.pools = pools
        self.pools_by_name = {p.name: p for p in pools}
        self.damage_order = damage_order

    def __getattr__(self, item):
        try:
            return self.__dict__["values"][item]
        except KeyError:
            raise AttributeError(
                f"'{item}' is not a need this server declares "
                f"(it declares: {', '.join(sorted(NEEDS_BY_NAME))})"
            ) from None

    @property
    def vital_pool(self):
        """The pool whose exhaustion takes a creature out of the fight."""
        for pool in self.pools:
            if pool.down_at is not None:
                return pool
        return None

    def fresh_pools(self, supplied=None):
        """The `pools` block for a newly made token.

        `supplied` is whatever the table typed in, by pool name. A pool
        the ruleset gives a starting maximum for uses that unless the
        table overrode it; one it does not gets what the table typed, or
        zero, which reads as a token nobody has filled in yet."""
        supplied = supplied or {}
        out = {}
        for pool in self.pools:
            maximum = supplied.get(pool.name, pool.starts)
            try:
                maximum = int(maximum)
            except (TypeError, ValueError):
                maximum = 0
            out[pool.name] = {"current": maximum, "max": maximum}
        return out

    def is_down(self, token) -> bool:
        pool = self.vital_pool
        if pool is None:
            return False
        block = (token.get("pools") or {}).get(pool.name)
        if not block:
            return False
        return block["current"] <= pool.down_at

    def as_json(self):
        """The ruleset as the client needs to see it: enough to draw the
        pools and label them, and to say what is being played."""
        return {
            "name": self.name,
            "version": self.version,
            "pools": [p.as_json() for p in self.pools],
            "damageOrder": list(self.damage_order),
            "gridSize": self.values["grid_size"],
            "defaultRoll": self.values["default_roll"],
        }

    def provenance(self):
        stamp = self.version or "unversioned"
        lines = [f"ruleset '{self.name}' {stamp} from {self.mechanics.directory}"]
        for need in NEEDS:
            lines.append(
                f"  {need.name:<20} {self.values[need.name]!r:<28} "
                f"{self.sources[need.name]}"
            )
        lines.append(f"  pools, in damage order: {', '.join(self.damage_order)}")
        for pool in self.pools:
            starts = ("the table supplies it" if pool.supplied_by_table
                      else f"starts at {pool.starts}")
            floor = "no floor" if pool.floor is None else f"floor {pool.floor}"
            down = "" if pool.down_at is None else f", down at {pool.down_at}"
            lines.append(f"    {pool.name:<16} {starts}, {floor}{down}")
        return "\n".join(lines)


def _resolve(value, mechanics, what):
    """A From comes out of the ruleset; anything else is already the
    value. A From naming a mechanic the ruleset has not got is a stale
    binding, and says so differently from a ruleset that never claimed
    to answer."""
    if not isinstance(value, From):
        return value
    if not mechanics.has(value.rule_id, value.key):
        raise RulesetUnplayable(
            f"the '{mechanics.name}' binding says {what} comes from "
            f"{value.rule_id}.{value.key}, and that ruleset has no such "
            f"mechanic. The binding in {Path(__file__).name} is out of date "
            "with the ruleset it names."
        )
    return mechanics.mech(value.rule_id, value.key)


def bind(name=None, path=None) -> Ruleset:
    """Load a ruleset and resolve every need and pool against it."""
    name = name or os.environ.get(RULESET_ENV) or DEFAULT_RULESET
    mechanics = load_ruleset(name, path=path)
    binding = BINDINGS.get(name)
    if binding is None:
        raise RulesetUnplayable(
            f"ruleset '{name}' is built, but this server has no binding for "
            f"it - nothing says which of its mechanics answers which of the "
            f"server's needs, or what pools a creature in it has. Bindings "
            f"exist for: {', '.join(sorted(BINDINGS))}. Add one to BINDINGS "
            f"in {Path(__file__).name}."
        )

    scalars = binding["scalars"]
    values, sources, unanswered = {}, {}, []
    for need in NEEDS:
        where = scalars.get(need.name)
        if where is not None:
            rule_id, key = where
            values[need.name] = _resolve(From(rule_id, key), mechanics, need.name)
            sources[need.name] = f"{name}:{rule_id}.{key}"
            continue
        if need.owner is TABLE:
            values[need.name] = need.fallback
            sources[need.name] = ("this server (the book is silent, and this "
                                  "is not a rules question)")
            continue
        unanswered.append(need)

    if unanswered:
        detail = "\n".join(f"  {n.name} - {n.why}" for n in unanswered)
        raise RulesetUnplayable(
            f"ruleset '{name}' does not answer "
            f"{len(unanswered)} thing(s) this server must know:\n{detail}\n"
            "These are rules questions, so the server will not invent them."
        )

    pools = tuple(
        BoundPool(
            name=p.name,
            label=p.label,
            starts=_resolve(p.starts, mechanics, f"pool '{p.name}' starting max"),
            floor=_resolve(p.floor, mechanics, f"pool '{p.name}' floor"),
            caps_at_max=bool(_resolve(p.caps_at_max, mechanics,
                                      f"pool '{p.name}' cap")),
            down_at=_resolve(p.down_at, mechanics, f"pool '{p.name}' down_at"),
        )
        for p in binding["pools"]
    )
    if not pools:
        raise RulesetUnplayable(
            f"the '{name}' binding declares no pools, so a creature in it "
            "would have no condition to track at all."
        )
    vital = [p for p in pools if p.down_at is not None]
    if len(vital) != 1:
        raise RulesetUnplayable(
            f"the '{name}' binding marks {len(vital)} pools with down_at, and "
            "exactly one has to say when a creature is out of the fight."
        )

    order = _resolve(binding["damage_order"], mechanics, "the damage order")
    order = tuple(order)
    known = {p.name for p in pools}
    unknown = [n for n in order if n not in known]
    if unknown:
        raise RulesetUnplayable(
            f"ruleset '{name}' takes damage in the order {list(order)}, which "
            f"names {unknown} - not a pool the '{name}' binding declares "
            f"(it declares: {', '.join(sorted(known))}). Either the ruleset "
            "renamed a pool or the binding never had it."
        )
    return Ruleset(mechanics, values, sources, pools, order)
