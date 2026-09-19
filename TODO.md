# TODO

Open work on the server and the toolset, roughly in the order it is
likely to be picked up. Nothing here is a commitment; it is a list of
things known to be missing so that they stop being rediscovered.

Finished work lives in [DONE.md](DONE.md), which is worth a look before
starting anything here: some of its entries record something that was
tried and found wanting, and those are the ones most likely to be
thought of again. An entry moves there only when nothing about it is
outstanding — one that was half done, however large the half, stays
here with the rest of it.

## How an entry moves

There are three places an entry can be, and the place it is in *is* its
status. Nothing carries a status field.

- **An area section** below — parked. Nobody is working on it.
- **In flight**, at the top — being worked on now. At most three, and
  the limit is the point: a fourth thing in flight means three things
  are half-finished, which is the state this file exists to prevent.
- **[DONE.md](DONE.md)** — finished, and worth reading before
  reopening anything near it.

Moving an entry is a cut and paste. Into In flight it stays inside this
file; out to `DONE.md` it crosses one. Either way the entry travels
whole, keeping the section heading it came from — the area headings are
mirrored in `DONE.md` for exactly that reason.

An entry in flight gains a **Now:** paragraph saying what is true as of
the last time it was touched, and may carry a checklist of the steps
still to take. The rule that makes this worth doing:

> **Now: is rewritten, never appended to.**

If something in a superseded **Now:** is worth keeping — a measurement,
a dead end, a reason an approach was abandoned — it moves into the body
of the entry or goes straight to `DONE.md`. Otherwise it goes. The
history of how an entry got to its present state is in git, which is
the tool for that; this file should read as a description of the
present. The alternative is what the rules project's `TODO.md` grew
without meaning to: entries three amendments deep, where knowing what
is currently true means reading the whole thing and working out which
sentence has not yet been contradicted.

A blocked entry is not a fourth place. It stays in flight with a
**Blocked:** line naming what it is waiting on, and it keeps occupying
one of the three slots — that is what makes a block cost something. If
it is going to be blocked for weeks, it goes back to its area section,
which is an honest statement that nobody is working on it.

Checklists belong inside an entry in flight, where the steps really are
small and atomic and get deleted along with the entry when it lands.
They are not for the entries themselves: an entry is a paragraph of
prose with a bold headline, because the prose is the part that is worth
having afterwards.

---

## In flight

*Nothing. Up to three entries may sit here; see above for what one
looks like when it arrives.*

---

## The rules engine

- **The server knows about no ruleset at all.** "The game" is a
  position, a hit point total and a generic dice roller. Turning a
  ruleset into `data.py` functions the way `roll_dice` and `set_hp`
  already are — validated in `server.py`, applied and persisted in
  `data.py` — is the largest single piece of work on this list, and
  most of the rest of this file is easier once it is decided. What the
  server would read is a ruleset's two build outputs, `snippets.json`
  and `mechanics.json`. There is already a worked pattern for carrying
  those into a consumer without a submodule: the adventures project
  commits its own stamped copy under `refs/rules-ico/`, and
  [SHARING.md](SHARING.md) records why a pin was declined. The
  ownership boundary comes with them — a mechanic value is measured
  against the whole system in `rules/ico/sim/`, so this server reads
  those numbers and never restates one.
- **Dice notation is `XdY+Z` and nothing else.** No advantage or
  disadvantage, no exploding dice, no pools. This is deliberately
  downstream of the entry above rather than a gap in its own right:
  which notations are worth parsing is a question the ruleset answers,
  and guessing now buys a parser for rolls nobody makes.

## State and persistence

- **`snapshot()` hands out the live state dict.** It returns `_state`
  itself rather than a copy, which is safe today only because its one
  caller serialises it immediately and throws the result away. It is
  the first thing standing in the way of two entries below — a
  per-player view of the board, and more than one game on one server.
  Both need `snapshot()` to become a projection of the state rather
  than the state.
- **Every mutation writes the whole game and tells everyone the whole
  game.** `_save()` JSON-dumps all of `_state` into one row on every
  change, and `broadcast_state()` emits all of it to every connected
  client. That is the right prototype answer and it is written down as
  such in README.md; it is named here because it is the thing that
  stops working first once a token carries a character sheet.
- **`turnOrder` is the expensive part of the relational migration.**
  README.md has the analysis — an index into a Python list becomes a
  `position` column and an `ORDER BY`, and `advance_turn()` stops being
  index arithmetic. Kept here as a pointer rather than restated, so
  there is one copy of the reasoning.
- **One room, one game.** Nothing namespaces the state, so a second
  group needs a second server. This is also the natural trigger for the
  relational migration above: "which room does this row belong to" is
  the question a JSON blob answers worst.
- **The log is capped at two hundred entries and the overflow is
  gone.** `_push_log` pops from the front, and the trimmed list is what
  gets persisted, so a long session's early history exists nowhere. No
  harm at prototype scale. A campaign log anybody wants to keep is its
  own table, and stops being part of the broadcast blob at the same
  time.

## The socket surface

- **There is no authentication of any kind.** Anyone with the URL joins
  as anyone, including as the DM, and `cors_allowed_origins` is `"*"`.
  Fine for people who are in the room with you and not fine for
  anything else, which is the whole of the reason this has not been
  exposed further.
- **Everyone is sent everything.** No fog of war, no line of sight, no
  DM-only layer. The mechanism is per-`sid` emits rather than a
  broadcast, plus something on a token saying who may see it; the
  prerequisite is `snapshot()` becoming a projection, above.
- **A reconnecting player gets a brand new token.** Tokens are
  deliberately left on the board when their owner disconnects so the DM
  can reseat a returning player, but nothing does the reseating
  automatically. Matching by name on `join` is the small version and is
  probably enough.
- **Nothing tests the server.** `tools/test_rules.py` is the toolset's,
  and it does not know this server exists. The event contract is
  exactly the sort of thing that is cheap to test and currently is not:
  who may move what, that a player cannot move somebody else's token,
  that HP clamps at both ends, that removing the token whose turn it is
  leaves `currentTurn` somewhere sane. The rules side of this project
  gets a lot of its confidence from a test suite that exercises the
  real ruleset; this side has none at all.

## The client

- **Every player is a hero and the DM picks from three shapes.**
  `data.MODEL_KINDS` is `hero`/`goblin`/`ogre`, players are forced to
  the first, and adding a shape means touching the tuple, `MODEL_URLS`
  in `index.html`, and the spawn dropdown. A character-select step on
  join is the player-facing half of the same change.
- **The assets are placeholders, and swapping them changes how cloning
  works.** The current rigs are pivot nodes with mesh children and no
  skeleton, so `template.clone(true)` is enough; a properly rigged pack
  needs `THREE.SkeletonUtils.clone()` or the skin bindings break. The
  work is known and costed — see `public/assets/README.md` — it has
  just not been done.
- **The map is a flat grid.** No map images, no elevation the client
  draws, no line of sight. Mostly waiting on the fog of war entry
  above, which decides what the client is allowed to know.

## The rules toolset

`rules-toolset/` lives in this repository but answers to a different
bar: [SHARING.md](SHARING.md) says an addition has to be in the
toolset's own vocabulary, usable by any ruleset, demonstrated in
`rules/demo/`, and covered by `tools/test_rules.py` against both
rulesets. That file also carries its own list of extensions that were
*declined*, with the reasoning, so that declining one is not the same
as forgetting it — check there before adding anything here.

- **`{% book-only %}` wants generalising into `{% gm-only %}`.** The
  adventures need a tag that strips by target the way `book-only`
  already does, and the right answer is one mechanism parameterised by
  target rather than two implementations of the same idea. Half of the
  work landed already — a corpus declares its audience tags and each
  target says what it does with each — so what is left is the
  adventure-side naming and whatever the adventure compiler needs from
  it. [WORKING.md](WORKING.md) flags this as seam work: it is designed
  on both sides at once, in one deliberately combined session, and the
  toolset is still edited here.
- **The adventure compiler has to reuse `rulesc/` rather than
  reimplement it.** Same seam, same rule about where it gets edited.
  Named here so that the toolset side of it is visible from this
  repository and not only from the other one.
