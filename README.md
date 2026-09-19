# RPG Table — Prototype (Python server)

Same game as the Node version — single-room, 3D grid battle-map, DM +
player roles — with the server rewritten in Python. Event names, state
shape, and game logic are a line-for-line port of `server.js`, so if
you've read that one this one will look very familiar.

This repository is also a dependency of other projects, which hold it
as a git submodule and extend `rules-toolset/` for their own document
kinds. `SHARING.md` says who may change what here, and what an addition
to the toolset has to satisfy to stay usable by every game that
compiles through it. `WORKING.md` says how to work across the three
projects — which working copy to open, when to keep the sessions
separate and when not, and step-by-step procedures for the common jobs.

## Stack

- **Server:** FastAPI + [python-socketio](https://python-socketio.readthedocs.io/)
  (ASGI mode) + Uvicorn. `python-socketio` speaks the same Socket.io
  wire protocol as the Node server did, so the client-side game logic
  didn't need to change — the client just points at whichever server
  answers `/socket.io/`.
- **Persistence:** SQLite (via `aiosqlite`), one row holding the whole
  game state as a JSON blob, rewritten on every mutation. See
  "Persistence design" below.
- **Client:** identical `public/index.html` from the Node version,
  with one change: it loads the Socket.io client library from a CDN
  (`cdn.socket.io`) instead of `/socket.io/socket.io.js`. The Node
  `socket.io` package serves that file itself; `python-socketio`
  doesn't, so the client needs to fetch it from somewhere else.

## Files

- **`server.py`** — Socket.io event handlers. Each one does exactly
  two things: check whether this `sid` is allowed to do what it's
  asking (role checks, ownership checks), then call into `data.py` and
  broadcast the result. No state mutation happens here.
- **`data.py`** — the data access layer. Owns the in-memory state dict,
  every function that reads or mutates it, and persistence to SQLite.
  This is the only file that knows the state is "a dict" — everything
  else just calls functions like `data.move_token(...)` or
  `data.get_player(sid)`.
- **`ruleset.py`** — which game this server is running, and where each
  of its numbers comes from. Declares the server's needs in the
  server's own vocabulary and maps each one onto a mechanic per
  ruleset. See below.
- **`test_server.py`** — the server's tests. `python3 test_server.py`.
- **`public/index.html`** — the 3D client. Loads three character
  models (`public/assets/models/*.glb`) once at startup, clones them
  per token, and animates them procedurally — see "3D models and
  animation" below. Also holds the character screen and the two
  smaller character views; see "Characters".
- **`public/assets/`** — the placeholder model/texture pack (hero,
  goblin, ogre, plus a ground texture). See its own README under
  `public/assets/` for how these were generated and how to swap in a
  real asset pack later.

## Where the game's numbers come from

Not from this code. Every game value the server uses is read at startup
from a compiled ruleset's `build/mechanics.json` — the same file the
book is generated from — so changing a rule and rebuilding moves the
book and the server's behaviour together. `data.py` carries no game
constant of its own, and `ruleset.bind()` raises at import rather than
defaulting, because a server that invents a number the book states is
the second source of truth this whole pipeline exists to prevent.

`ruleset.py` holds the mapping, in three parts:

- **`NEEDS`** — single values the server needs, in its own words:
  `grid_size`, `default_roll`, and so on. Each is marked as belonging to
  the **rules** or to the **table**.
- **`BINDINGS[<ruleset>]["scalars"]`** — which mechanic answers each
  need, per ruleset.
- **`BINDINGS[<ruleset>]["pools"]`** — the tracks a creature's condition
  is kept on, and the damage order through them.

A need the ruleset does not answer is handled by which half it is in. A
**table**-owned one — how wide the battle map is, how many dice one
click may roll — the server answers itself and says so in the startup
log, because the book has no opinion and should not be made to have
one. A **rules**-owned one is a refusal: the server will not start, and
names what is missing.

### Pools, and why a token stopped having `hp`

A token used to carry `hp` and `maxHp`. It now carries a `pools` block,
one entry per track the ruleset declares, and which tracks those are is
never decided here. `demo` declares one, called hit points. Ico
declares four:

```
pools, in damage order: mastery, core
  mastery     the table supplies it, floor 0
  core        the table supplies it, no floor, down at 0
  stamina     the table supplies it, floor 0
  spirit      the table supplies it, floor 0
```

Three things in that are worth reading twice, because each is the
ruleset saying something the server would otherwise have had to invent:

- **The damage order comes out of the book.** It is read from
  `hit-points.damage_order`, so mastery absorbs a blow before core does
  because Ico says so, not because `data.py` says so. Note that stamina
  and spirit are not in the order at all — they are conditions of a
  creature in the way hit points are, which is why they are pools, but
  nothing damages them directly.
- **Core has no floor.** Hit points clamping at zero was a demo rule all
  along. Ico's core hit points run *past* zero — death's door is zero
  and death itself is at negative constitution — so the server clamps
  nothing there and lets the value go negative. What zero means is
  carried separately, as the threshold a creature is out of the fight
  at.
- **No Ico pool has a starting maximum.** All four derive from a
  character: core equals constitution, stamina and spirit are based on
  attributes, mastery is bought. A token has no attributes, so the
  *table* supplies these per token — which is what a virtual tabletop is
  for, and is exactly where this rung stops and the next one begins.

### Where a maximum comes from

Three of Ico's four maxima are not typed in at all — they are computed
from the creature's attributes, and which attribute is again the book's
to say:

| pool | binding reads | which says | so the max is |
|---|---|---|---|
| core | `hit-points.core_hp_equals` | `constitution` | the creature's constitution |
| stamina | `power-sources.stamina_base` | `constitution` | the same |
| spirit | `power-sources.spirit_base` | `willpower` | the creature's willpower |
| mastery | — | — | typed in: it is *bought* |

So a token carries an `attributes` block too, and setting constitution
moves core and stamina with it. That is the whole of the formula
language and it is deliberately not a language: a `Attribute(From(...))`
resolves a mechanic whose *value is an attribute name*, and looks that
attribute up. `notes.md`'s case against a DSL is that anything powerful
enough to express a real ruleset is a programming language, and you end
up writing an interpreter and a debugger for an audience of one. An
indirection through a name the book already states is not that.

Two consequences worth knowing:

- **A derived maximum can be overridden, and then it stops following.**
  Ico states stamina and spirit as a *base* that advancement widens, so
  the derived figure is the floor of a real character's maximum rather
  than the whole of it. `power-sources.md`'s own example is Sela, base
  spirit 15, widened to 27. Set a maximum by hand and it stays; clear
  it and it goes back to following the attribute.
- **Binding checks that a derived attribute exists.** A mechanic naming
  an attribute the ruleset has not got is a dangling reference that
  prose hides — "a character's will" reads as English whatever the
  attribute list says. This check is what found
  `power-sources.spirit_base` saying `will` when the six attributes are
  strength, dexterity, constitution, intelligence, willpower and
  charisma.

The client is told all of this with every state, so the spawn form
grows a box per attribute and a box only for the pools nothing derives
— one, for Ico — and the initiative list draws a chip per pool with a
marker on the computed ones, without any of it knowing what a mastery
hit point is.

Pick a ruleset with `$RPG_RULESET` (default `demo`, the one that ships
in `rules/` and the one this server has in fact always been
implementing). The lookup is the toolset's, so an installed ruleset in
`rules/<name>/` wins over one being authored outside, and
`$RULESET_PATH` adds a third place to look.

## Characters

A **character** is stored apart from any token, because it outlives the
fight it was on the map for: one player may have several, and a
character nobody is currently playing still exists. `data.py` keeps
them in `_state["characters"]`, persisted with everything else.

**A token that names a character has no pools or attributes of its
own.** `data._sheet()` sends every read and write to the character
instead, so a wound taken in this fight is a wound on the sheet next
session, and there is one set of current values rather than two that
drift. Unlink it and the token keeps the numbers it was playing with —
the sheet is gone, the creature is still standing there.

A sheet holds its attributes, its pools as current-and-maximum (derived
from the attributes exactly as a token's are), its equipment in three
slots — wielded, worn, carried — and free-form skills, disciplines,
powers and notes.

### What is checked, and what is not

`ruleset.py`'s `Character` block declares the budgets the book states
and the catalogues it carries: the attribute spread and its floor and
ceiling, the starting purse, the hand count, and the documents whose
dict-valued mechanics are items. An item is a mechanic whose value is a
block — `weapons.dagger` is one, `weapons.finesse_size` is not — which
is a distinction in the toolset's shape rather than in any game, so
only the list of catalogues had to be named.

From that the server counts three things and **remarks** on them:

| | against |
|---|---|
| attribute points spread | `character-creation.attribute_points` |
| gold of equipment | `character-creation.starting_gold` |
| hands of wielded gear | `free-hands.hands_total` |

**Remarks, never refusals.** A table that has applied priorities
legitimately has more than the standard attribute points — the rules
say so — and a DM may hand a player anything they like. A virtual
tabletop that refused to store a character its DM had approved would be
wrong about what it is for.

Skills, disciplines and powers are stored and shown and checked by
nobody. They are real systems with budgets of their own, and a server
that half-enforced them would be worse than one that plainly does not.

### Three views

One record, three sizes, none of which knows what an attribute or a
pool means — the names, labels, budgets and catalogue all arrive in
`state.ruleset`:

- **Abbreviated** — `sheetBrief()` / `briefText()`. A line: name, every
  pool as current-over-maximum, what is in hand. Used as the hover on
  an initiative row.
- **Middle** — `renderCharSide()`. A sidebar panel: the line above, the
  three equipment slots, purse and hands against their budgets, and any
  remarks.
- **Detailed** — `renderCharScreen()`. Its own screen, and the same
  form that writes a character up in the first place. A pool that
  follows an attribute shows the figure the book computes; type a
  maximum to override it, clear the maximum to hand it back.

Pool edits on the character screen go out as the ordinary token pool
events rather than as a sheet update, so "this creature took a hit" has
one code path whether it was hit on the map or edited on the sheet.

## 3D models and animation

Tokens now render as real (if blocky/placeholder) 3D characters
instead of colored cylinders. Every token has a `kind` field
(`"hero"`, `"goblin"`, or `"ogre"`) chosen server-side: players always
get `"hero"`; the DM picks a monster's kind from a dropdown when
spawning it. The client preloads all three `.glb` models before
allowing anyone to join (there's a short "Loading assets…" state on
the login screen) and clones the right template for each token as it
appears in `syncScene()`.

**Movement now tweens instead of teleporting**, and plays a walk cycle
while it does: each token tracks a `displayPos` (what's actually
rendered) and a `targetPos` (where the server says it is), and the
render loop lerps one toward the other every frame. While they differ,
the model's named pivot nodes (`*_LeftLegPivot`, `*_RightArmPivot`,
etc. — see the asset pack's README) get a sine-wave walk cycle; once
they match, it settles into a small idle sway instead. None of this is
server state — it's purely a client-side rendering choice, same as the
turn-highlight ring that still sits under each token.

**Why plain `.clone()` works here:** these placeholder rigs have no
skeleton/skin — each limb is a pivot node plus a mesh child, not
bone-weighted geometry — so reusing one loaded model across many
tokens is just `template.clone(true)`. A properly rigged pack (Mixamo,
etc.) would need `THREE.SkeletonUtils.clone()` instead, since a plain
clone breaks skin bindings. Worth knowing before you swap in real
assets — see the asset pack README for the fuller version of this
trade-off.

## Persistence design

State is snapshotted to a single SQLite row (`game_state`, one JSON
blob column) on every mutation — a full server restart resumes exactly
where the game left off. SQLite over a plain JSON file because a crash
mid-write leaves the previous good snapshot intact instead of a
corrupted file, and it needs no separate service to run.

**One deliberate exception: `players` is never persisted.** A
Socket.io session id (`sid`) is only valid for the lifetime of one
connection — a saved `sid` can never reconnect after a restart. So
`data.load()` restores `tokens`, `turnOrder`, `currentTurn`, and `log`,
but always starts `players` empty; people just rejoin, and a fresh
`sid` gets attached to them then. (Tokens deliberately aren't deleted
when their owner disconnects, so a DM can reseat a returning player
onto their existing character — matching a rejoining player back to
their old token by name is a reasonable next step, not implemented
here.)

## Migrating to full relational later

The `data.py` split exists specifically to make this cheap when you
need it. Every handler in `server.py` calls functions like
`data.move_token(token_id, x, y)` or `data.spawn_token(...)` — it
never touches the state shape directly. That means a move from "one
JSON blob" to real `players`/`tokens`/`log` tables is a rewrite of the
*insides* of the functions in `data.py` (swap dict mutation for SQL,
swap `snapshot()`'s dict-copy for a query that reassembles the same
shape from joined tables) — not a rewrite of `server.py`, and no
change to the client at all, since the wire format (`state` events)
stays identical either way.

The one place that migration will actually cost you effort:
`turnOrder` is a Python list today (`append`, index into
`currentTurn`, modulo to advance). Relationally that becomes an
ordered relationship — a `position` column plus `ORDER BY` — and
`advance_turn()` goes from "index arithmetic" to "count rows, compute
the next position, update." That's the one function worth budgeting
real time for; everything else in `data.py` is close to a mechanical
port.

## Run it

Requires Python 3.9+.

```bash
cd rpg-master
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

Open `http://localhost:3000` — same as before: one tab as DM, one per
player. LAN/tunnel notes are the same as the Node version's README.
A `game.db` SQLite file appears alongside `server.py` on first run —
delete it any time to reset the campaign to a blank board.

Alternative run command (equivalent, useful if you want autoreload
during development):

```bash
uvicorn server:app --reload --port 3000
```

Note: with `--reload`, Uvicorn imports your app object by string
(`server:app`), so `data.load()` runs from FastAPI's `startup` event
either way — no change needed to use autoreload.

## What changed vs. the Node version, and why

| Node                          | Python                                  |
|-------------------------------|------------------------------------------|
| `express` static file serving | `FastAPI` + `StaticFiles` mounted at `/` |
| `socket.io` server package    | `python-socketio` `AsyncServer` (ASGI)   |
| `http.createServer` + listen  | `uvicorn.run(app, ...)`                  |
| Callbacks per `socket.on(...)`| `async def` handlers via `@sio.event`, matched by function name (e.g. `async def moveToken(sid, data)` handles the `"moveToken"` event) |
| In-memory `state` object, mutated directly in handlers | Same shape, moved into `data.py` behind function calls, snapshotted to SQLite on every change |

Everything about *game logic* — clamping to the grid, turn order,
who's allowed to move what — started as a direct port from the Node
version rather than a rewrite. Two things have since moved away from
it, both described above: the numbers all come from a ruleset now, and
a token carries a pool per track its ruleset declares rather than one
`hp` and one `maxHp`. Against `demo` the behaviour is still the Node
version's, because `demo` states the Node version's numbers. The other
structural addition beyond the port is the `server.py`/`data.py` split
and the SQLite persistence described above — the Node version doesn't
have either.

## What I'd extend first

The roadmap moved to [TODO.md](TODO.md), which is a board rather than a
document: an entry there can be picked up, worked on and finished, and
finishing it moves it to [DONE.md](DONE.md). Keeping the list here as
well would mean two copies to move an entry in, and one of them would
be wrong within a week. What stays in this file is what the server *is*
— the sections above, and the rough edges below.

## Known rough edges (prototype-level, on purpose)

- No fog of war, no line-of-sight, no map images — flat grid only.
- Dice notation is basic (`XdY+Z`) — no advantage/disadvantage or
  exploding dice. The syntax and its limits come from the ruleset, so
  a ruleset could widen them; none does yet.
- No authentication — trust-based, for people you're actually playing
  with. Anyone with the URL can join as anyone, including as DM.
- Single room — one game per running server.
- Character models are placeholder-quality (see
  `public/assets/README.md`) and only three shapes exist.
- A dropped player's token stays on the board but isn't reclaimed on
  rejoin; they'll get a brand-new token unless you extend `join` to
  match by name (see [TODO.md](TODO.md)).
