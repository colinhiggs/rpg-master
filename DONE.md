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

- **A creature has the tracks its ruleset says it has.** A token used
  to carry `hp` and `maxHp`. It carries a `pools` block now, one entry
  per track the ruleset declares — one for `demo`, four for Ico
  (mastery, core, stamina, spirit) — and `data.py` decides none of
  them.

  **Why one field could not be stretched.** Ico takes damage on two
  tracks in a stated order, and pays for powers out of two more. No
  reading of a single `hp` covers that, which is why the rung-0 binding
  could not answer `starting_hp` for Ico at all and refused to start.
  It binds now.

  **Three things the ruleset turned out to say that the server had been
  assuming.** The damage order is read from `hit-points.damage_order`,
  so mastery absorbs a blow before core because Ico says so; stamina
  and spirit are deliberately not in that order, being conditions
  rather than damage tracks. Core has **no floor** — clamping hit
  points at zero was a `demo` rule all along, and Ico's core runs past
  zero toward death at negative constitution, so the threshold for
  being out of the fight is carried separately from any clamp. And no
  Ico pool states a starting maximum, because all four derive from a
  character sheet the server does not hold, so the table types them in.

  **Where the rung stops.** `apply_damage` walks a sequence the book
  states; it computes nothing. That is the line: executing declared
  data is rung 1, and deriving core hit points from constitution is
  rung 2 and deliberately not here.

  Verified end to end in the browser against Ico 2.6.1: a spawn form
  that grows a box per pool, damage spilling mastery into core, core
  going to −2 and the token greying out at death's door. 76 server
  tests, up from 38.

## State and persistence

*Nothing yet.*

## The socket surface

*Nothing yet.*

## The client

*Nothing yet.*

## The rules toolset

*Nothing yet.*
