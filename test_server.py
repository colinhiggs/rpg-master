# test_server.py — tests for the server's half of the rules pipeline.
#
# Run: ./venv/bin/python test_server.py
#
# The toolset's tools/test_rules.py proves that a value exists in
# exactly one place inside a ruleset. These prove the other end of it:
# that the server reads those values rather than carrying its own, that
# a creature has the tracks its ruleset says it has, and that the
# binding naming all of it has not gone stale against the ruleset.
#
# That last one is the point. The accessor layer this replaces was
# correct when written and silently wrong for months afterwards,
# because nothing ever asserted that the keys it named still existed.
# One test below would have caught it the day the ruleset moved — and
# it now covers pools and the damage order too, not just the scalars,
# because those name mechanics the same way.
#
# The same harness as test_rules.py, deliberately: check(), a count, a
# non-zero exit. No test framework to install.

import asyncio
import io
import sys
import tempfile
from pathlib import Path

import ruleset
from rulesc.runtime import RulesNotBuilt, load_ruleset
from rulesc import RuleError

passed, failed = 0, 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc as e:
        return str(e)
    except Exception:
        return None
    return None


def mechanic_refs(binding):
    """Every mechanic a binding names, wherever it names one: scalars,
    any pool property, and the damage order."""
    refs = [(rid, key) for rid, key in binding["scalars"].values()]
    for pool in binding["pools"]:
        for attr in ("starts", "floor", "caps_at_max", "down_at"):
            value = getattr(pool, attr)
            if isinstance(value, ruleset.From):
                refs.append((value.rule_id, value.key))
    if isinstance(binding["damage_order"], ruleset.From):
        refs.append((binding["damage_order"].rule_id,
                     binding["damage_order"].key))
    return refs


print("\nWhat the server declares it needs:")

check("every need is owned by the rules or the table",
      all(n.owner in (ruleset.RULES, ruleset.TABLE) for n in ruleset.NEEDS))
check("every table-owned need carries the value the table would use",
      all(n.fallback is not None
          for n in ruleset.NEEDS if n.owner is ruleset.TABLE))
check("no rules-owned need carries a fallback, so none can be invented",
      all(n.fallback is None
          for n in ruleset.NEEDS if n.owner is ruleset.RULES))
check("need names are unique",
      len(ruleset.NEEDS_BY_NAME) == len(ruleset.NEEDS))


print("\nEvery binding names mechanics that exist:")

for name, binding in sorted(ruleset.BINDINGS.items()):
    mechanics = load_ruleset(name)
    refs = mechanic_refs(binding)
    stale = [f"{rid}.{key}" for rid, key in refs if not mechanics.has(rid, key)]
    check(f"the '{name}' binding is current against the built ruleset",
          not stale, ", ".join(stale))
    check(f"the '{name}' binding names mechanics somewhere at all",
          len(refs) > 0)
    unknown = sorted(set(binding["scalars"]) - set(ruleset.NEEDS_BY_NAME))
    check(f"the '{name}' binding names only needs the server declares",
          not unknown, ", ".join(unknown))
    check(f"the '{name}' binding marks exactly one pool as the vital one",
          sum(1 for p in binding["pools"] if p.down_at is not None) == 1)
    check(f"the '{name}' binding gives every pool a distinct name",
          len({p.name for p in binding["pools"]}) == len(binding["pools"]))


print("\nA ruleset with one pool:")

demo = ruleset.bind("demo")
check("demo resolves every need", set(demo.values) == set(ruleset.NEEDS_BY_NAME))
check("and every one of them came from the book, not the table",
      all(src.startswith("demo:") for src in demo.sources.values()))
check("it has exactly one pool", len(demo.pools) == 1)
check("which the book gives a starting maximum for",
      demo.pools[0].starts == 20 and not demo.pools[0].supplied_by_table)
check("and which is the one you go down on",
      demo.vital_pool is demo.pools[0])
check("a fresh token gets it full",
      demo.fresh_pools()["hp"] == {"current": 20, "max": 20})
check("the provenance names the pools and their order",
      "damage order" in demo.provenance() and "hp" in demo.provenance())
check("an undeclared need is an AttributeError, not a silent None",
      raises(AttributeError, lambda: demo.no_such_need) is not None)


print("\nA ruleset with four:")

ico = ruleset.bind("ico")
check("ico binds at all, which it could not before pools existed",
      ico.name == "ico")
check("it carries its version", ico.version == load_ruleset("ico").version)
check("it has four pools",
      [p.name for p in ico.pools] == ["mastery", "core", "stamina", "spirit"])
check("the damage order came out of the book, not out of the binding",
      ico.damage_order == ("mastery", "core"))
check("so the power sources are not damage pools",
      "stamina" not in ico.damage_order and "spirit" not in ico.damage_order)
check("core is the pool you go down on",
      ico.vital_pool.name == "core")
check("death's door came from the book", ico.vital_pool.down_at == 0)
check("and core has no floor, because Ico's runs past zero",
      ico.vital_pool.floor is None)
check("mastery does have a floor", ico.pools_by_name["mastery"].floor == 0)
check("no pool has a starting maximum the book can state",
      all(p.supplied_by_table for p in ico.pools))
check("so a fresh token comes up empty, for the table to fill in",
      all(b == {"current": 0, "max": 0} for b in ico.fresh_pools().values()))
check("and takes what the table typed when it types some",
      ico.fresh_pools({"core": 12, "mastery": 8})["core"]
      == {"current": 12, "max": 12})
check("the grid is the table's, since a map width is not a rule of Ico",
      "this server" in ico.sources["grid_size"])
check("but the die is the book's",
      ico.sources["default_roll"] == "ico:core-resolution.standard_die")


print("\nFailing usefully:")

check("a ruleset that does not exist says where it looked",
      "Looked in" in (raises(RuleError, ruleset.bind, "no-such-ruleset") or ""))
check("a ruleset that exists but is not built says to build it",
      "build.py" in (raises(RulesNotBuilt, load_ruleset, "demo-supplement") or ""))
check("a missing mechanic names what the ruleset does have instead",
      "it has:" in (raises(KeyError, load_ruleset("ico").mech,
                           "movement", "grid_size") or ""))

_saved = ruleset.BINDINGS["demo"]["damage_order"]
try:
    ruleset.BINDINGS["demo"]["damage_order"] = ("hp", "ectoplasm")
    msg = raises(ruleset.RulesetUnplayable, ruleset.bind, "demo")
    check("a damage order naming a pool that does not exist is caught",
          msg is not None and "ectoplasm" in msg)
finally:
    ruleset.BINDINGS["demo"]["damage_order"] = _saved

_saved_pools = ruleset.BINDINGS["demo"]["pools"]
try:
    ruleset.BINDINGS["demo"]["pools"] = ()
    check("a ruleset with no pools at all is refused",
          "no pools" in (raises(ruleset.RulesetUnplayable,
                                ruleset.bind, "demo") or ""))
    ruleset.BINDINGS["demo"]["pools"] = (
        ruleset.Pool("a", "A", down_at=0), ruleset.Pool("b", "B", down_at=0))
    check("two pools claiming to be the vital one is refused",
          "exactly one" in (raises(ruleset.RulesetUnplayable,
                                   ruleset.bind, "demo") or ""))
finally:
    ruleset.BINDINGS["demo"]["pools"] = _saved_pools

_stale = ruleset.Pool("hp", "Hit points",
                      starts=ruleset.From("damage-and-healing", "gone_away"),
                      down_at=0)
try:
    ruleset.BINDINGS["demo"]["pools"] = (_stale,)
    check("a pool bound to a mechanic that has gone says the binding is stale",
          "out of date" in (raises(ruleset.RulesetUnplayable,
                                   ruleset.bind, "demo") or ""))
finally:
    ruleset.BINDINGS["demo"]["pools"] = _saved_pools


print("\nWhat data.py does with it:")

import data  # noqa: E402  — after the binding tests, so a failure reports above

check("the grid comes from the ruleset",
      data._state["gridSize"] == data.RULES.grid_size)
check("the dice syntax comes from the ruleset",
      data.DICE_RE.pattern == data.RULES.dice_notation)
check("the client is told what game it is playing",
      data._state["ruleset"]["name"] == data.RULES.name)
check("and is given the pools to draw",
      [p["name"] for p in data._state["ruleset"]["pools"]]
      == [p.name for p in data.RULES.pools])
check("a roll of the ruleset's default notation is accepted",
      data.roll_dice(data.RULES.default_roll) is not None)
check("a roll past the ruleset's dice limit is refused",
      data.roll_dice(f"{data.RULES.max_dice_per_roll + 1}d6") is None)
check("a roll past the ruleset's die-size limit is refused",
      data.roll_dice(f"1d{data.RULES.max_sides + 1}") is None)

source = io.open("data.py", encoding="utf-8").read()
for literal, what in [("GRID_SIZE = 14", "the grid size"),
                      ('"hp": 20', "starting hit points"),
                      ("<= 100)", "the dice limit"),
                      (r're.compile(r"^(\d*)d', "the dice syntax")]:
    check(f"data.py no longer carries its own copy of {what}",
          literal not in source, literal)

# The old single-total fields survive in exactly one place: the function
# that converts a token saved before pools existed. Anywhere else would
# be a leftover.
_migration = source[source.index("def _migrate_token"):]
_migration = _migration[:_migration.index("\n\n\n")]
check("the old hit point fields live only in the migration",
      source.count('"maxHp"') == _migration.count('"maxHp"')
      and source.count('"maxHp"') > 0,
      f"{source.count(chr(34) + 'maxHp' + chr(34))} in file, "
      f"{_migration.count(chr(34) + 'maxHp' + chr(34))} in the migration")

server_source = io.open("server.py", encoding="utf-8").read()
check("server.py no longer carries its own default roll",
      '"d20"' not in server_source)
check("and no longer has a single-hit-point-total handler",
      "async def setHp" not in server_source)


async def _demo_state():
    global data
    import importlib
    import os
    os.environ["RPG_RULESET"] = "demo"
    importlib.reload(ruleset)
    data = importlib.reload(data)
    with tempfile.TemporaryDirectory() as tmp:
        data.DB_PATH = Path(tmp) / "test.db"
        await data.init_db()
        tid = await data.add_player("sid-1", "Ashri", "player")
        tok = data.get_token(tid)
        check("a joining player's token starts full on the book's value",
              tok["pools"]["hp"] == {"current": 20, "max": 20})
        await data.apply_damage(tid, 5)
        check("damage comes off the one pool there is",
              data.get_token(tid)["pools"]["hp"]["current"] == 15)
        await data.apply_damage(tid, 999)
        check("and stops at the floor the book states",
              data.get_token(tid)["pools"]["hp"]["current"] == 0)
        check("at which point the creature is down", data.is_down(data.get_token(tid)))
        await data.heal(tid, 999)
        check("healing stops at the maximum, because the book caps it",
              data.get_token(tid)["pools"]["hp"]["current"] == 20)
        check("and it is up again", not data.is_down(data.get_token(tid)))

        # A token saved before pools existed.
        data._state["tokens"]["old"] = {
            "id": "old", "name": "Legacy", "x": 1, "y": 1, "color": "#fff",
            "kind": "goblin", "hp": 7, "maxHp": 12, "ownerId": None,
            "isNpc": True,
        }
        migrated = data._migrate_token(data._state["tokens"]["old"])
        check("a token saved before pools is brought forward",
              migrated["pools"]["hp"] == {"current": 7, "max": 12})
        check("and loses the fields that no longer mean anything",
              "hp" not in migrated and "maxHp" not in migrated)


async def _ico_state():
    global data
    import importlib
    import os
    os.environ["RPG_RULESET"] = "ico"
    importlib.reload(ruleset)
    data = importlib.reload(data)
    with tempfile.TemporaryDirectory() as tmp:
        data.DB_PATH = Path(tmp) / "test.db"
        await data.init_db()
        tid = await data.spawn_token("Goblin", "#999",
                                     {"mastery": 6, "core": 10,
                                      "stamina": 8, "spirit": 4},
                                     2, 2, "goblin")
        tid = tid["id"]
        tok = data.get_token(tid)
        check("a spawned creature gets every pool the table typed",
              {k: v["max"] for k, v in tok["pools"].items()}
              == {"mastery": 6, "core": 10, "stamina": 8, "spirit": 4})

        await data.apply_damage(tid, 4)
        tok = data.get_token(tid)
        check("damage takes mastery first, because the book says so",
              tok["pools"]["mastery"]["current"] == 2
              and tok["pools"]["core"]["current"] == 10)
        await data.apply_damage(tid, 5)
        tok = data.get_token(tid)
        check("it spills into core once mastery is gone",
              tok["pools"]["mastery"]["current"] == 0
              and tok["pools"]["core"]["current"] == 7)
        check("and leaves the power sources alone",
              tok["pools"]["stamina"]["current"] == 8
              and tok["pools"]["spirit"]["current"] == 4)
        await data.apply_damage(tid, 7)
        check("core reaching death's door is being down",
              data.is_down(data.get_token(tid)))
        await data.apply_damage(tid, 3)
        check("and core keeps going past zero, because Ico has no floor there",
              data.get_token(tid)["pools"]["core"]["current"] == -3)

        await data.heal(tid, 5)
        tok = data.get_token(tid)
        check("healing comes back through core first, reversing the order",
              tok["pools"]["core"]["current"] == 2
              and tok["pools"]["mastery"]["current"] == 0)
        await data.heal(tid, 100)
        tok = data.get_token(tid)
        check("and fills both, stopping at each maximum",
              tok["pools"]["core"]["current"] == 10
              and tok["pools"]["mastery"]["current"] == 6)

        await data.set_pool(tid, "spirit", 99)
        check("a pool set above its maximum is capped",
              data.get_token(tid)["pools"]["spirit"]["current"] == 4)
        await data.set_pool_max(tid, "spirit", 2)
        check("lowering a maximum brings the current value down with it",
              data.get_token(tid)["pools"]["spirit"]["current"] == 2)
        check("a pool the ruleset does not have is refused",
              await data.set_pool(tid, "ectoplasm", 1) is None)


print("\nOne pool, end to end:")
asyncio.run(_demo_state())
print("\nFour pools, end to end:")
asyncio.run(_ico_state())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
