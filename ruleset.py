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


class Attribute:
    """A value that equals one of the creature's attributes, where the
    RULESET says which one.

    `hit-points.core_hp_equals` is the string "constitution", so core
    hit points are not bound to constitution here - they are bound to
    whatever that mechanic names, and the server looks the attribute up
    on the creature. Rename the attribute in the book and this follows;
    name one that does not exist and binding refuses to start, which is
    how `power-sources.spirit_base` was found saying "will" when the
    six attributes are strength, dexterity, constitution, intelligence,
    willpower and charisma.

    This is the whole of the formula language, deliberately. notes.md's
    case against a DSL is that a language powerful enough to express a
    real ruleset is a programming language, and you end up writing an
    interpreter and a debugger for an audience of one. An indirection
    through a name the book already states is not that."""

    def __init__(self, names):
        self.names = names          # a From, whose value is an attribute name

    def __repr__(self):
        return f"Attribute({self.names!r})"


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
                 death's door.
    derives      an Attribute, when the book says what this pool's
                 maximum equals. A derived maximum is computed from the
                 creature rather than typed in, and recomputed when the
                 attribute it depends on changes. The table can still
                 override it - see BoundPool.max_for - because a pool
                 the rules let a character widen has a maximum the
                 formula is only the base of."""

    def __init__(self, name, label, starts=None, floor=None,
                 caps_at_max=True, down_at=None, derives=None):
        self.name = name
        self.label = label
        self.starts = starts
        self.derives = derives
        self.floor = floor
        self.caps_at_max = caps_at_max
        self.down_at = down_at


class Character:
    """What a ruleset says about building and carrying a character.

    Optional: a game can be played at this table without having any
    character rules the server knows about, which is `demo`, and then
    the server offers no character screen for it rather than inventing
    one.

    Everything here is a budget or a catalogue — a number the book
    states and a list the book carries. None of it is a rule the server
    works out. The checks it drives WARN and never block: a table that
    has applied priorities legitimately has more than the standard
    attribute points, and a virtual tabletop that refused to store a
    character its DM had approved would be wrong about what it is for."""

    def __init__(self, attribute_budget=None, attribute_min=None,
                 attribute_max=None, purse=None, hands=None,
                 two_handed_size=None, catalogues=(), cost_key=None,
                 size_key=None, hands_key=None):
        self.attribute_budget = attribute_budget
        self.attribute_min = attribute_min
        self.attribute_max = attribute_max
        self.purse = purse
        self.hands = hands
        self.two_handed_size = two_handed_size
        self.catalogues = catalogues
        self.cost_key = cost_key
        self.size_key = size_key
        self.hands_key = hands_key


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
        # demo has no attributes, so nothing in it can derive from one.
        # Its pool keeps the flat starting value the book states, and
        # the derivation machinery below simply never fires.
        "attributes": (),
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
    # Three of the four maxima are now DERIVED, from attributes the
    # token carries and mechanics that name which attribute:
    #
    #   core      equals constitution outright - hit-points.md says so
    #             in as many words and nothing widens it.
    #   stamina   BASED ON constitution, and spirit on willpower. The
    #             word in the book is "base": advancement widens both,
    #             so the derived figure is the floor of a character's
    #             real maximum rather than the whole of it. A table that
    #             has spent points overrides it, and the override sticks.
    #
    # mastery derives from nothing, and that is the book being clear
    # rather than the binding being lazy: mastery hit points are BOUGHT
    # as a character is built and advanced. There is no attribute to
    # read, so the table types it, which is what typing it in is for.
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
        "attributes": (From("attributes", "physical"),
                       From("attributes", "mental")),
        "pools": (
            Pool("mastery", "Mastery", floor=0),
            Pool("core", "Core", floor=None,
                 derives=Attribute(From("hit-points", "core_hp_equals")),
                 down_at=From("dying", "deaths_door_at_core")),
            Pool("stamina", "Stamina", floor=0,
                 derives=Attribute(From("power-sources", "stamina_base"))),
            Pool("spirit", "Spirit", floor=0,
                 derives=Attribute(From("power-sources", "spirit_base"))),
        ),
        "damage_order": From("hit-points", "damage_order"),
        # Building a character, and what it can carry. Every entry is a
        # number the book states or a table the book carries.
        #
        # `catalogues` names documents whose dict-valued mechanics are
        # items: weapons.dagger is a dict and so is an item, while
        # weapons.finesse_size is a string and so is not. That rule is
        # the toolset's shape rather than Ico's, which is why the
        # catalogue list is the only Ico-specific part of it.
        #
        # Two hands is the budget a wielded item spends against, and an
        # item of the two-handed size spends both. Ico states both
        # numbers; the server multiplies nothing.
        "character": Character(
            attribute_budget=From("character-creation", "attribute_points"),
            attribute_min=From("character-creation", "attribute_min"),
            attribute_max=From("character-creation", "attribute_max"),
            purse=From("character-creation", "starting_gold"),
            hands=From("free-hands", "hands_total"),
            two_handed_size=From("weapons", "two_handed_size"),
            catalogues=("weapons", "ranged-weapons", "armour"),
            cost_key="cost_gp",
            size_key="size",
            # The ranged weapons state their hands outright; the melee
            # ones leave it to size. Read the stated one where there is
            # one, and fall back to size where there is not, rather than
            # picking one convention and being wrong about half the
            # table.
            hands_key="hands",
        ),
    },
}


class RulesetUnplayable(Exception):
    """The chosen ruleset does not answer something the server must know."""


class BoundPool:
    """A Pool with everything resolved against the ruleset."""

    def __init__(self, name, label, starts, floor, caps_at_max, down_at,
                 derives_from=None):
        self.name = name
        self.label = label
        self.starts = starts
        self.floor = floor
        self.caps_at_max = caps_at_max
        self.down_at = down_at
        self.derives_from = derives_from    # an attribute name, or None

    @property
    def supplied_by_table(self):
        return self.starts is None and self.derives_from is None

    def max_for(self, attributes):
        """This pool's maximum for a creature with these attributes, or
        None if nothing but the table can say."""
        if self.derives_from is not None:
            return int((attributes or {}).get(self.derives_from, 0))
        return self.starts

    def as_json(self):
        """What the client needs to draw and edit this pool."""
        return {
            "name": self.name,
            "label": self.label,
            "starts": self.starts,
            "floor": self.floor,
            "capsAtMax": self.caps_at_max,
            "downAt": self.down_at,
            "derivesFrom": self.derives_from,
        }

    def clamp(self, value, maximum):
        if self.caps_at_max and value > maximum:
            value = maximum
        if self.floor is not None and value < self.floor:
            value = self.floor
        return value


class BoundCharacter:
    """A Character with every budget resolved and every catalogue read."""

    def __init__(self, spec, items, attribute_budget, attribute_min,
                 attribute_max, purse, hands, two_handed_size):
        self.spec = spec
        self.items = items                  # id -> item dict
        self.attribute_budget = attribute_budget
        self.attribute_min = attribute_min
        self.attribute_max = attribute_max
        self.purse = purse
        self.hands = hands
        self.two_handed_size = two_handed_size

    def item(self, item_id):
        return self.items.get(item_id)

    def cost_of(self, item_id):
        item = self.items.get(item_id)
        return 0 if item is None else int(item.get("cost") or 0)

    def hands_for(self, item_id):
        """How many hands wielding this spends. An item of the size the
        book calls two-handed takes both; anything else takes one."""
        item = self.items.get(item_id)
        if item is None:
            return 1
        if item.get("hands") is not None:
            return int(item["hands"])
        if self.two_handed_size is not None \
                and item.get("size") == self.two_handed_size:
            return 2
        return 1

    def as_json(self):
        return {
            "attributeBudget": self.attribute_budget,
            "attributeMin": self.attribute_min,
            "attributeMax": self.attribute_max,
            "purse": self.purse,
            "hands": self.hands,
            "items": self.items,
        }


class Ruleset:
    """The bound ruleset: every need and every pool resolved, with the
    provenance kept so that startup can say where each came from."""

    def __init__(self, mechanics, values, sources, pools, damage_order,
                 attributes=(), character=None):
        self.mechanics = mechanics
        self.name = mechanics.name
        self.version = mechanics.version
        self.values = values
        self.sources = sources
        self.pools = pools
        self.pools_by_name = {p.name: p for p in pools}
        self.damage_order = damage_order
        self.attributes = attributes
        self.character = character

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

    def fresh_attributes(self, supplied=None):
        """The `attributes` block for a newly made token. Nothing derives
        an attribute — they are the character, and everything else hangs
        off them — so these are the table's to supply, always."""
        supplied = supplied or {}
        out = {}
        for name in self.attributes:
            try:
                out[name] = int(supplied.get(name, 0))
            except (TypeError, ValueError):
                out[name] = 0
        return out

    def fresh_pools(self, supplied=None, attributes=None):
        """The `pools` block for a newly made token.

        Three ways a maximum can arrive, in order of precedence: the
        table typed one, the book derives one from an attribute, or the
        book states a flat one. A block records which happened, because
        a derived maximum has to follow its attribute and an overridden
        one has to stop following it."""
        supplied = supplied or {}
        out = {}
        for pool in self.pools:
            if pool.name in supplied and supplied[pool.name] not in (None, ""):
                maximum, derived = supplied[pool.name], False
            else:
                maximum, derived = pool.max_for(attributes), \
                                   pool.derives_from is not None
            try:
                maximum = int(maximum)
            except (TypeError, ValueError):
                maximum, derived = 0, False
            out[pool.name] = {"current": maximum, "max": maximum,
                              "derived": derived}
        return out

    def recompute_pools(self, token) -> bool:
        """Bring a token's derived maxima back in line with its
        attributes. Called when an attribute moves; a pool the table has
        overridden is left alone, which is the point of recording that
        it was overridden."""
        changed = False
        attributes = token.get("attributes") or {}
        for pool in self.pools:
            if pool.derives_from is None:
                continue
            block = (token.get("pools") or {}).get(pool.name)
            if block is None or not block.get("derived"):
                continue
            maximum = pool.max_for(attributes)
            if maximum != block["max"]:
                # Undamaged stays undamaged. A creature sitting at its
                # maximum has taken nothing, so raising the maximum
                # raises it too — which is also what makes a character
                # written up attribute by attribute come out whole
                # rather than at nought out of thirteen. Anything below
                # its maximum has taken a wound, and keeps it.
                was_whole = block["current"] >= block["max"]
                block["max"] = maximum
                block["current"] = pool.clamp(
                    maximum if was_whole else block["current"], maximum)
                changed = True
        return changed

    def is_down(self, token) -> bool:
        pool = self.vital_pool
        if pool is None:
            return False
        block = (token.get("pools") or {}).get(pool.name)
        if not block:
            return False
        return block["current"] <= pool.down_at

    # -- characters --------------------------------------------------
    def fresh_character(self, name="New character", attributes=None,
                        equipment=None):
        """A character, with its pools derived from its attributes the
        same way a token's are. A character is stored apart from any
        token: it outlives the fight it was on the map for, and one
        player may have several."""
        attrs = self.fresh_attributes(attributes)
        equipment = equipment or {}
        return {
            "name": str(name or "New character")[:48],
            "attributes": attrs,
            "pools": self.fresh_pools(None, attrs),
            "equipment": {
                slot: [str(i) for i in (equipment.get(slot) or [])]
                for slot in ("wielded", "worn", "carried")
            },
            # Stored and shown, checked by nobody. Ico's skills,
            # disciplines and powers are real systems with budgets of
            # their own, and a server that half-enforced them would be
            # worse than one that plainly does not.
            "skills": {},
            "disciplines": {},
            "powers": [],
            "notes": "",
            # Set when a player's token is pointed at this sheet, so a
            # returning player can be given it again. Not identity: the
            # table has no authentication and this is a convenience, not
            # a claim about who anybody is.
            "lastPlayedBy": None,
        }

    def check_character(self, char):
        """What is odd about this character, as a list of remarks.

        Never a refusal. A table that has applied priorities has more
        than the standard attribute points by the rules' own design, and
        a DM may hand a character anything they like — so these say what
        the book's numbers are and leave the judgement where it
        belongs."""
        spec = self.character
        if spec is None:
            return []
        out = []
        attrs = char.get("attributes") or {}

        spent = sum(int(v or 0) for v in attrs.values())
        if spec.attribute_budget is not None and spent != spec.attribute_budget:
            over = spent - spec.attribute_budget
            out.append({
                "level": "warn" if over > 0 else "note",
                "text": (f"{spent} attribute points spread, against a budget of "
                         f"{spec.attribute_budget}"
                         + (f" — {over} over. Priorities can buy more; nothing "
                            "else can." if over > 0
                            else f" — {-over} unspent.")),
            })
        for attr, value in attrs.items():
            value = int(value or 0)
            if spec.attribute_min is not None and value < spec.attribute_min:
                out.append({"level": "warn",
                            "text": f"{attr} is {value}, below the minimum of "
                                    f"{spec.attribute_min}"})
            if spec.attribute_max is not None and value > spec.attribute_max:
                out.append({"level": "warn",
                            "text": f"{attr} is {value}, above the starting "
                                    f"maximum of {spec.attribute_max}. Fine "
                                    "after a race modifier or advancement."})

        equipment = char.get("equipment") or {}
        carried = [i for slot in ("wielded", "worn", "carried")
                   for i in equipment.get(slot, [])]
        unknown = sorted({i for i in carried if spec.item(i) is None})
        if unknown:
            out.append({"level": "warn",
                        "text": "not in any catalogue: " + ", ".join(unknown)})
        spend = sum(spec.cost_of(i) for i in carried)
        if spec.purse is not None and spend > spec.purse:
            out.append({"level": "warn",
                        "text": f"{spend} gold of equipment, against a starting "
                                f"purse of {spec.purse}"})

        hands = sum(spec.hands_for(i) for i in equipment.get("wielded", []))
        if spec.hands is not None and hands > spec.hands:
            out.append({"level": "warn",
                        "text": f"wielding {hands} hands' worth with "
                                f"{spec.hands} hands"})
        return out

    def character_totals(self, char):
        """The numbers the views want to show whether or not anything is
        wrong with them."""
        spec = self.character
        if spec is None:
            return {}
        equipment = char.get("equipment") or {}
        carried = [i for slot in ("wielded", "worn", "carried")
                   for i in equipment.get(slot, [])]
        return {
            "attributesSpent": sum(int(v or 0)
                                   for v in (char.get("attributes") or {}).values()),
            "goldSpent": sum(spec.cost_of(i) for i in carried),
            "handsUsed": sum(spec.hands_for(i)
                             for i in equipment.get("wielded", [])),
        }

    def as_json(self):
        """The ruleset as the client needs to see it: enough to draw the
        pools and label them, and to say what is being played."""
        return {
            "name": self.name,
            "version": self.version,
            "attributes": list(self.attributes),
            "character": self.character.as_json() if self.character else None,
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
        lines.append("  attributes: " + (", ".join(self.attributes) or "none"))
        lines.append(f"  pools, in damage order: {', '.join(self.damage_order)}")
        for pool in self.pools:
            if pool.derives_from is not None:
                starts = f"equals {pool.derives_from}"
            elif pool.starts is not None:
                starts = f"starts at {pool.starts}"
            else:
                starts = "the table supplies it"
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

    # The attributes a creature in this game has. The names come out of
    # the ruleset, so a game that calls them something else, or has none
    # at all, needs nothing here.
    attributes = []
    for source in binding.get("attributes", ()):
        names = _resolve(source, mechanics, "the attribute list")
        if isinstance(names, str):
            names = [names]
        for attr in names:
            if attr not in attributes:
                attributes.append(attr)
    attributes = tuple(attributes)

    pools = []
    for p in binding["pools"]:
        derives_from = None
        if p.derives is not None:
            derives_from = _resolve(p.derives.names, mechanics,
                                    f"pool '{p.name}' derivation")
            # The check that matters. A mechanic naming an attribute the
            # ruleset has not got is a dangling reference, and prose
            # hides it: "a character's will" reads as English whatever
            # the attribute list says. This is what caught
            # power-sources.spirit_base saying 'will'.
            if derives_from not in attributes:
                raise RulesetUnplayable(
                    f"ruleset '{name}' says pool '{p.name}' equals "
                    f"'{derives_from}' ({p.derives.names.rule_id}."
                    f"{p.derives.names.key}), and '{derives_from}' is not one "
                    f"of its attributes ({', '.join(attributes) or 'it has none'}). "
                    "Either the ruleset means an attribute it does not have, "
                    "or the binding is reading the wrong mechanic."
                )
        pools.append(BoundPool(
            name=p.name,
            label=p.label,
            starts=_resolve(p.starts, mechanics, f"pool '{p.name}' starting max"),
            floor=_resolve(p.floor, mechanics, f"pool '{p.name}' floor"),
            caps_at_max=bool(_resolve(p.caps_at_max, mechanics,
                                      f"pool '{p.name}' cap")),
            down_at=_resolve(p.down_at, mechanics, f"pool '{p.name}' down_at"),
            derives_from=derives_from,
        ))
    pools = tuple(pools)
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

    # Items. A dict-valued mechanic in a declared catalogue is an item;
    # a scalar one is a rule about the catalogue and is not. That is a
    # distinction in the toolset's shape rather than in any game, which
    # is why only the list of catalogues had to be named here.
    character = None
    spec = binding.get("character")
    if spec is not None:
        items = {}
        for catalogue in spec.catalogues:
            block = mechanics.rules.get(catalogue)
            if block is None:
                raise RulesetUnplayable(
                    f"the '{name}' binding lists '{catalogue}' as an item "
                    f"catalogue and the ruleset has no such document "
                    f"(it has: {', '.join(sorted(mechanics.rules))})."
                )
            for key, value in block.items():
                if not isinstance(value, dict):
                    continue
                items[f"{catalogue}.{key}"] = {
                    "id": f"{catalogue}.{key}",
                    "catalogue": catalogue,
                    "label": key.replace("_", " "),
                    "cost": value.get(spec.cost_key),
                    "size": value.get(spec.size_key),
                    "hands": value.get(spec.hands_key),
                    "stats": value,
                }
        if not items:
            raise RulesetUnplayable(
                f"the '{name}' binding names {list(spec.catalogues)} as item "
                "catalogues and not one of them holds an item. An item is a "
                "mechanic whose value is a block; these hold only scalars."
            )
        character = BoundCharacter(
            spec=spec,
            items=items,
            attribute_budget=_resolve(spec.attribute_budget, mechanics,
                                      "the attribute budget"),
            attribute_min=_resolve(spec.attribute_min, mechanics,
                                   "the attribute minimum"),
            attribute_max=_resolve(spec.attribute_max, mechanics,
                                   "the attribute maximum"),
            purse=_resolve(spec.purse, mechanics, "the starting purse"),
            hands=_resolve(spec.hands, mechanics, "the hand count"),
            two_handed_size=_resolve(spec.two_handed_size, mechanics,
                                     "the two-handed size"),
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
    return Ruleset(mechanics, values, sources, pools, order, attributes,
                   character)
