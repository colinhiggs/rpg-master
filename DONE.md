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

- **A pool's maximum is computed from the creature, where the book
  says how.** Three of Ico's four are: core hit points equal
  constitution, stamina is based on constitution and spirit on
  willpower. Mastery is not, and that is the book being clear rather
  than the binding being lazy — mastery hit points are bought.

  **The mechanism, and why it is not a language.** A pool may declare
  `Attribute(From("hit-points", "core_hp_equals"))`. That mechanic's
  *value* is the string `constitution`, so the binding resolves the
  mechanic to an attribute name and the server looks that attribute up
  on the token. Rename the attribute in the book and this follows.
  `notes.md`'s case against a DSL is that anything powerful enough for
  a real ruleset is a programming language with an interpreter and a
  debugger for an audience of one; an indirection through a name the
  book already states is not that, and it covers every derivation Ico
  expresses this way.

  **Override, and why it is needed.** Stamina and spirit are stated as
  a *base* that advancement widens, so a derived figure is the floor of
  a real character's maximum rather than the whole of it —
  `power-sources.md`'s example is Sela at base spirit 15, widened to
  27. A maximum set by hand stops following its attribute; cleared, it
  starts again. A pool records which of the two it is, because a
  recompute has to know.

  **What it found on its first run.** `power-sources.spirit_base` said
  `will`, and `will` is not one of Ico's six attributes. Every other
  reference in the ruleset says `willpower`, including the worked
  example two paragraphs below the value. It survived because prose
  interpolates it as "a character's will", which reads as English
  rather than as a dangling reference, and because `sim/model.py` takes
  `char.attributes["willpower"]` directly instead of looking the name
  up — so the one consumer that could have caught it was not using it.
  Fixed in the rules repository; the gates did not move, as they could
  not have.

  The spawn form is the visible result: six attribute boxes and one
  pool box, where before there were four pool boxes. 98 server tests,
  up from 76.

## State and persistence

*Nothing yet.*

## The socket surface

*Nothing yet.*

## Characters

- **Characters are stored, generated and viewed.** A character is its
  own record, not a token: it outlives the fight it was on the map for,
  one player may have several, and one nobody is playing still exists.
  It holds attributes, pools as current-and-maximum, equipment in three
  slots — wielded, worn, carried — and free-form skills, disciplines,
  powers and notes.

  **The load-bearing decision is that a linked token has no pools of
  its own.** `data._sheet()` sends every read and write to the
  character, so a wound taken in this fight is on the sheet next
  session and there is one set of current values rather than two that
  drift. Unlink and the token keeps the numbers it was playing with:
  the sheet is gone, the creature is still standing there.

  **What is checked was settled deliberately.** The server counts three
  things against budgets the book states — attribute points spread,
  gold of equipment, hands of wielded gear — and *remarks* on them.
  Never refuses. A table that has applied priorities legitimately has
  more than the standard eighty points, by the rules' own design, and a
  virtual tabletop that refused to store a character its DM had
  approved would be wrong about what it is for. Skills, disciplines and
  powers are stored and shown and validated by nobody: they are real
  systems with budgets of their own, and half-enforcing them would be
  worse than plainly not.

  **Items came out of the catalogue rule rather than a list.** A
  mechanic whose value is a block is an item; a scalar one is a rule
  about the catalogue. `weapons.dagger` is an item, `weapons.finesse_size`
  is not. That distinction is the toolset's shape rather than any
  game's, so the only Ico-specific part is which three documents to
  read — and 29 items fall out of them with their costs. Hands work the
  same way twice over: the ranged weapons state `hands` outright and the
  melee ones leave it to `size` against `two_handed_size`, so the
  binding reads the stated one where there is one rather than picking a
  convention and being wrong about half the table.

  Three views, none of which knows what an attribute is: a line for a
  hover, a sidebar panel, and a full screen that doubles as the form
  that writes a character up. Pool edits on that screen go out as the
  ordinary token events, so "this creature took a hit" has one code
  path whether it happened on the map or on the sheet.

  One thing fixed on the way: `recompute_pools` clamped a current value
  down with its maximum but never carried it up, so a character written
  up attribute by attribute came out at nought of thirteen. Undamaged
  now stays undamaged. 132 server tests, up from 98.

- **A returning player picks up what they were playing.** Two entries
  on the board turned out to be one fix: a reconnecting player used to
  get a brand new token, and nothing linked a player to their character
  across sessions.

  **Why the old answer could not work.** `ownerId` is a socket id. It
  dies with the connection, so after a drop — or a restart, where
  `players` is deliberately never restored — there was nothing left to
  say whose a token had been. A token now carries a durable
  `playerName`, and a character carries `lastPlayedBy` once a player's
  token has been pointed at it.

  **Three steps on join, in order.** A token going spare with this
  player's name, picked up with whatever character and whatever wounds
  were on it. Failing that, a character that remembers them — for when
  the token was removed but the sheet outlived it, which is the whole
  reason a character is stored apart from a token — and they get a new
  token named after the character and linked to it. Failing that, a new
  token, as before.

  **A token somebody is currently connected as is never taken.** Two
  people at one table typing the same name get one each, and the second
  does not shoulder the first out of their own character.

  The name is the identity, because the table has no authentication and
  deliberately none yet: it is the same thing a table goes by out loud,
  and it is a convenience rather than a claim about who anybody is.
  Somebody who knows a name can pick up that character, which is the
  same trust every other event on this server already assumes.

  A side effect worth having: the initiative order stops growing. A
  rejoining player used to append a second entry to it.

  Verified through a full server restart, not just a reload: same
  token, same sheet, same wound. 145 server tests, up from 132.

## The client

*Nothing yet.*

## The rules toolset

*Nothing yet.*
