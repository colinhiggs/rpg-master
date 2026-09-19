# Done

Finished work, kept rather than deleted. This is not a completed column
that nobody reads — it is the first place to look before starting
anything in [TODO.md](TODO.md), because an entry here may record
something that was tried, measured and found wanting, and that is the
expensive thing to rediscover.

An entry arrives from `TODO.md` only when nothing about it is
outstanding. One that is half done, however large the half, stays
there. It keeps the area heading it came from, so the headings below
mirror `TODO.md`'s exactly and are added here as entries arrive.

What an entry should say, if it is worth saying at all: what was
wanted, what was built, and what was rejected on the way and why. The
**Now:** line an entry carried while it was in flight does not come
with it — that line was always about the present, and the present has
moved on. Anything in it still worth keeping is written into the body
of the entry before it moves.

Note that some finished work is recorded elsewhere on purpose and is
not copied here. [SHARING.md](SHARING.md) carries the toolset
extensions that landed *and* the ones that were declined, both with
their reasoning, because that file is where somebody proposing the next
extension will be reading. README.md carries the design decisions that
describe how the server works now rather than how it got there.

---

## The rules engine

- **The server reads its game numbers from the ruleset, and the reader
  is tested against one.** `data.py` used to hardcode a grid size, a
  starting hit point total, a dice regex and two roller limits. All of
  them now come from a compiled `build/mechanics.json` at import, and
  the server refuses to start rather than defaulting.

  **What was actually wrong.** A reader for this existed from the
  initial commit — `tools/rules_runtime.py`, with ten accessors like
  `starting_hp()` and `grid_size()`. Three documents described it as
  done: `notes.md` scored the values rung "Done", this repository's
  README called it "written and tested", and `sim/model.py`'s header
  cited it as the pattern it followed. It resolved 10 of 10 against
  `rules/demo` and 0 of 10 against `ico`. Nothing imported it and no
  test named it.

  The reason it rotted is the part worth keeping. Naming
  `damage-and-healing.starting_hp` is knowing a particular game, and
  `SHARING.md` forbids that inside `rules-toolset/`. The only ruleset
  the file could legally name keys from was the toolset's own fixture —
  and the fixture had been written to describe `data.py`'s constants
  (`movement.grid_size` is 14, `damage-and-healing.starting_hp` is 20,
  `dice-rolls.notation_pattern` is byte-identical to the old `DICE_RE`).
  So the loop closed on itself and proved nothing, and no
  game-agnostic test could have caught it, because there was nothing
  game-agnostic left to assert.

  **What replaced it.** The generic half is `rulesc/runtime.py` —
  finding a built ruleset, reading its `_version` stamp, and failing
  with the keys it did find. It names no rule and no mechanic. The
  half that names them is `ruleset.py` in this repository, which is
  allowed to know which game it is running, and which splits a need the
  book must answer from one the table may answer itself. A
  table-owned answer is printed at startup rather than assumed.

  **What it bought beyond the wiring.** Running against `ico` produces
  the rung-1 list rather than an estimate of it: two needs unanswered,
  `starting_hp` and `healing_caps_at_max`, both the same fact about one
  hit point pool versus two. And `test_server.py` exists — 38 tests,
  the first the server has ever had — of which the load-bearing one
  asserts that every binding names mechanics the ruleset still has. One
  test of that kind would have caught the original the day the ruleset
  moved.

## State and persistence

*Nothing yet.*

## The socket surface

*Nothing yet.*

## The client

*Nothing yet.*

## The rules toolset

*Nothing yet.*
