# test_server.py — tests for the server's half of the rules pipeline.
#
# Run: python3 test_server.py
#
# The toolset's tools/test_rules.py proves that a value exists in
# exactly one place inside a ruleset. These prove the other end of it:
# that the server reads those values rather than carrying its own, and
# that the binding saying which mechanic answers which need has not
# gone stale against the ruleset it names.
#
# That last one is the point. The accessor layer this replaces was
# correct when written and silently wrong for months afterwards,
# because nothing ever asserted that the keys it named still existed.
# One test below would have caught it the day the ruleset moved.
#
# The same harness as test_rules.py, deliberately: check(), a count, a
# non-zero exit. No test framework to install — this repository has no
# dependencies beyond the server's own.

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
    """Return the exception message, or None if it did not raise."""
    try:
        fn(*args, **kwargs)
    except exc as e:
        return str(e)
    except Exception:
        return None
    return None


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
    stale = [f"{need}->{rid}.{key}" for need, (rid, key) in binding.items()
             if not mechanics.has(rid, key)]
    check(f"the '{name}' binding is current against the built ruleset",
          not stale, ", ".join(stale))
    unknown = sorted(set(binding) - set(ruleset.NEEDS_BY_NAME))
    check(f"the '{name}' binding names only needs the server declares",
          not unknown, ", ".join(unknown))


print("\nBinding a ruleset that answers everything:")

demo = ruleset.bind("demo")
check("demo resolves every need", set(demo.values) == set(ruleset.NEEDS_BY_NAME))
check("and every one of them came from the book, not the table",
      all(src.startswith("demo:") for src in demo.sources.values()),
      str(sorted(s for s in demo.sources.values() if not s.startswith("demo:"))))
check("the provenance lists every need",
      all(n.name in demo.provenance() for n in ruleset.NEEDS))
check("an undeclared need is an AttributeError, not a silent None",
      raises(AttributeError, lambda: demo.no_such_need) is not None)
check("demo is unversioned, and that is reported rather than faked",
      demo.version is None)


print("\nBinding a ruleset that does not:")

msg = raises(ruleset.RulesetUnplayable, ruleset.bind, "ico")
check("ico refuses to bind", msg is not None)
check("and names starting_hp as the reason", msg and "starting_hp" in msg)
check("and names healing_caps_at_max as the other",
      msg and "healing_caps_at_max" in msg)
check("and does not complain about anything the table can answer",
      msg and "grid_size" not in msg and "max_sides" not in msg)
check("the two it can answer are genuinely bound",
      ruleset.BINDINGS["ico"]["default_roll"] == ("core-resolution", "standard_die")
      and ruleset.BINDINGS["ico"]["min_hp"] == ("dying", "deaths_door_at_core"))
check("ico carries its version, so the server could say what it is running",
      load_ruleset("ico").version is not None)


print("\nFailing usefully:")

check("a ruleset that does not exist says where it looked",
      (raises(RuleError, ruleset.bind, "no-such-ruleset") or "").find("Looked in") >= 0)
check("a ruleset that exists but is not built says to build it",
      "build.py" in (raises(RulesNotBuilt, load_ruleset, "demo-supplement") or ""))
check("a built ruleset with no binding says so rather than guessing",
      "no binding" in (raises(ruleset.RulesetUnplayable,
                              ruleset.bind, "demo-supplement") or "")
      or "has not been compiled" in (raises(RulesNotBuilt, ruleset.bind,
                                            "demo-supplement") or ""))
check("a missing mechanic names what the ruleset does have instead",
      "it has:" in (raises(KeyError, load_ruleset("ico").mech,
                           "movement", "grid_size") or ""))


print("\nWhat data.py does with it:")

import data  # noqa: E402  — imported here so a binding failure is reported above

check("the grid comes from the ruleset",
      data._state["gridSize"] == data.RULES.grid_size)
check("the dice syntax comes from the ruleset",
      data.DICE_RE.pattern == data.RULES.dice_notation)
check("a roll of the ruleset's default notation is accepted",
      data.roll_dice(data.RULES.default_roll) is not None)
check("a roll past the ruleset's dice limit is refused",
      data.roll_dice(f"{data.RULES.max_dice_per_roll + 1}d6") is None)
check("a roll past the ruleset's die-size limit is refused",
      data.roll_dice(f"1d{data.RULES.max_sides + 1}") is None)
check("one under each limit is still allowed",
      data.roll_dice(f"{data.RULES.max_dice_per_roll}d{data.RULES.max_sides}")
      is not None)

source = io.open("data.py", encoding="utf-8").read()
for literal, what in [("GRID_SIZE = 14", "the grid size"),
                      ('"hp": 20', "starting hit points"),
                      ("<= 100)", "the dice limit"),
                      ("<= 1000)", "the die-size limit"),
                      (r're.compile(r"^(\d*)d', "the dice syntax")]:
    check(f"data.py no longer carries its own copy of {what}",
          literal not in source, literal)

server_source = io.open("server.py", encoding="utf-8").read()
check("server.py no longer carries its own default roll",
      '"d20"' not in server_source)


async def _exercise_state():
    with tempfile.TemporaryDirectory() as tmp:
        data.DB_PATH = Path(tmp) / "test.db"
        await data.init_db()
        data._state["tokens"] = {}
        data._state["turnOrder"] = []
        data._state["players"] = {}
        data._state["log"] = []
        token_id = await data.add_player("sid-1", "Ashri", "player")
        token = data.get_token(token_id)
        check("a joining player's token starts on the ruleset's hit points",
              token["hp"] == data.RULES.starting_hp
              and token["maxHp"] == data.RULES.starting_hp)
        await data.set_hp(token_id, -999)
        check("hit points clamp down to the ruleset's floor",
              data.get_token(token_id)["hp"] == data.RULES.min_hp)
        await data.set_hp(token_id, 10 ** 6)
        expected = (data.RULES.starting_hp if data.RULES.healing_caps_at_max
                    else 10 ** 6)
        check("and up to the maximum, when the ruleset caps healing there",
              data.get_token(token_id)["hp"] == expected)


asyncio.run(_exercise_state())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
