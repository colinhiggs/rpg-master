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
- **`public/index.html`** — the 3D client. Loads three character
  models (`public/assets/models/*.glb`) once at startup, clones them
  per token, and animates them procedurally — see "3D models and
  animation" below.
- **`public/assets/`** — the placeholder model/texture pack (hero,
  goblin, ogre, plus a ground texture). See its own README under
  `public/assets/` for how these were generated and how to swap in a
  real asset pack later.

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
cd rpg-prototype-python
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

Everything about *game logic* — clamping to the grid, the dice-notation
regex, turn order, HP bounds, who's allowed to move what — is a direct
port from the Node version, not a rewrite, so behavior should match
exactly. The one structural addition beyond the port is the
`server.py`/`data.py` split and the SQLite persistence described above
— the Node version doesn't have either.

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
  exploding dice.
- No authentication — trust-based, for people you're actually playing
  with. Anyone with the URL can join as anyone, including as DM.
- Single room — one game per running server.
- Character models are placeholder-quality (see
  `public/assets/README.md`) and only three shapes exist.
- A dropped player's token stays on the board but isn't reclaimed on
  rejoin; they'll get a brand-new token unless you extend `join` to
  match by name (see [TODO.md](TODO.md)).
