# data.py — Data access layer for the RPG server.
#
# Every read/mutation of game state goes through this module instead of
# socket handlers touching a shared dict directly. Today that "database"
# is a dict snapshotted to SQLite on every write. If this ever grows into
# a normalized relational schema, the functions below are what change —
# their signatures stay the same, so server.py and the client don't have
# to. See README.md ("Migrating to full relational") for the full case.
#
# Concurrency note: Socket.io's AsyncServer runs handlers on a single
# asyncio event loop, so there's no risk of two handlers interleaving
# mid-mutation — each `await data.foo(...)` call completes before the
# next event is processed. That's what makes it safe for each mutator
# below to read-modify-write the module-level `_state` dict directly.

import json
import random
import re
import time
from pathlib import Path

import aiosqlite

import ruleset

# Every game number below comes from the compiled ruleset, and binding
# happens at import so that a missing one is a startup crash naming the
# mechanic rather than a game that quietly contradicts its own book.
# ruleset.py says which mechanic answers which need, and which of these
# the book has no opinion about. Nothing in this file may hardcode a
# value RULES could supply — that is the second source of truth the
# whole pipeline exists to prevent.
RULES = ruleset.bind()

DB_PATH = Path(__file__).parent / "game.db"

DICE_RE = re.compile(RULES.dice_notation, re.IGNORECASE)

# Which 3D model a token renders as on the client. Kept as a small
# fixed set (rather than a free-text field) so a bad/typo'd value from
# a client can't reference a model the client doesn't have — see
# spawn_token()'s validation below.
MODEL_KINDS = ("hero", "goblin", "ogre")

# ---------------------------------------------------------------------
# In-memory state — the single source of truth while the server runs.
# Persistence below exists to survive restarts, not to replace this.
# ---------------------------------------------------------------------
_state = {
    "gridSize": RULES.grid_size,
    "players": {},   # sid -> { id, name, role, tokenId }  — NOT persisted, see load()
    "tokens": {},    # tokenId -> { id, name, x, y, color, hp, maxHp, ownerId, isNpc }
    "turnOrder": [],
    "currentTurn": -1,
    "log": [],
}
_next_token_id = 1


def snapshot() -> dict:
    """The full state, exactly as broadcast to clients. Cheap: it's just
    the dict socket.io was already going to serialize to JSON."""
    return _state


# ---------------------------------------------------------------------
# Persistence — one row, one JSON blob, SQLite for crash-safe writes.
# ---------------------------------------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS game_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL,
                next_token_id INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )"""
        )
        await db.commit()


async def load():
    """Call once at startup, before accepting connections. Restores
    tokens/turnOrder/log from the last save; players are intentionally
    NOT restored — a socket id (sid) from a previous process can never
    reconnect, so an empty `players` map is the only state that makes
    sense for a fresh process. Tokens survive so the DM can resume the
    board and have players rejoin their existing characters (matching
    by name is a reasonable next step — not implemented here)."""
    global _state, _next_token_id
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT data, next_token_id FROM game_state WHERE id = 1") as cur:
            row = await cur.fetchone()
    if row:
        saved = json.loads(row[0])
        _state["gridSize"] = saved.get("gridSize", RULES.grid_size)
        _state["tokens"] = saved.get("tokens", {})
        _state["turnOrder"] = saved.get("turnOrder", [])
        _state["currentTurn"] = saved.get("currentTurn", -1)
        _state["log"] = saved.get("log", [])
        _state["players"] = {}  # always fresh — see docstring above
        _next_token_id = row[1]
    return _state


async def _save():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO game_state (id, data, next_token_id, updated_at)
               VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 data = excluded.data,
                 next_token_id = excluded.next_token_id,
                 updated_at = excluded.updated_at""",
            (json.dumps(_state), _next_token_id, int(time.time())),
        )
        await db.commit()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _clamp_to_grid(v: float) -> int:
    return max(0, min(_state["gridSize"] - 1, round(v)))


def _next_token_id_str() -> str:
    global _next_token_id
    tid = str(_next_token_id)
    _next_token_id += 1
    return tid


def _push_log(who: str, text: str) -> None:
    _state["log"].append({"who": who, "text": text, "ts": int(time.time() * 1000)})
    if len(_state["log"]) > 200:
        _state["log"].pop(0)


def get_player(sid):
    return _state["players"].get(sid)


def get_token(token_id):
    return _state["tokens"].get(token_id)


def current_turn_token_id():
    ct = _state["currentTurn"]
    order = _state["turnOrder"]
    if ct < 0 or ct >= len(order):
        return None
    return order[ct]


def roll_dice(notation: str):
    """Pure — no state touched, so no persistence needed. Kept here to
    keep server.py free of game-logic details, not because it reads
    or writes `_state`."""
    m = DICE_RE.match(notation.strip())
    if not m:
        return None
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    mod = int(m.group(3)) if m.group(3) else 0
    if not (1 <= count <= RULES.max_dice_per_roll) or not (
            2 <= sides <= RULES.max_sides):
        return None
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + mod
    return {"rolls": rolls, "mod": mod, "total": total, "notation": notation.strip()}


# ---------------------------------------------------------------------
# Mutators — every one of these is a unit of work: change `_state`,
# persist it, return whatever the caller needs. server.py's job is
# auth/validation (is this sid allowed to do this?); this module's job
# is applying the change once it's been allowed.
# ---------------------------------------------------------------------
async def add_player(sid: str, name: str, role: str):
    name = str(name or "Adventurer")[:24]
    role = "dm" if role == "dm" else "player"

    token_id = None
    if role == "player":
        token_id = _next_token_id_str()
        colors = ["#4f8ef7", "#f75f4f", "#4ff77e", "#f7d34f", "#c14ff7", "#4ff7e6"]
        _state["tokens"][token_id] = {
            "id": token_id,
            "name": name,
            "x": _clamp_to_grid(_state["gridSize"] / 2 + (random.random() * 4 - 2)),
            "y": _clamp_to_grid(_state["gridSize"] / 2 + (random.random() * 4 - 2)),
            "color": colors[len(_state["players"]) % len(colors)],
            "kind": "hero",
            "hp": RULES.starting_hp,
            "maxHp": RULES.starting_hp,
            "ownerId": sid,
            "isNpc": False,
        }
        _state["turnOrder"].append(token_id)

    _state["players"][sid] = {"id": sid, "name": name, "role": role, "tokenId": token_id}
    _push_log("system", f"{name} joined as {'Dungeon Master' if role == 'dm' else 'a player'}.")
    await _save()
    return token_id


async def remove_player(sid: str):
    player = _state["players"].pop(sid, None)
    if player:
        _push_log("system", f"{player['name']} disconnected.")
        # Token is deliberately left in place — see load()'s docstring.
        await _save()
    return player


async def move_token(token_id: str, x: float, y: float):
    token = _state["tokens"].get(token_id)
    if not token:
        return None
    token["x"] = _clamp_to_grid(x)
    token["y"] = _clamp_to_grid(y)
    await _save()
    return token


async def spawn_token(name: str, color: str, hp, x, y, kind: str = "goblin"):
    token_id = _next_token_id_str()
    try:
        hp_val = int(hp) if hp is not None else 10
    except (TypeError, ValueError):
        hp_val = 10
    if kind not in MODEL_KINDS:
        kind = "goblin"
    token = {
        "id": token_id,
        "name": str(name or "Monster")[:24],
        "x": _clamp_to_grid(x if x is not None else _state["gridSize"] / 2),
        "y": _clamp_to_grid(y if y is not None else _state["gridSize"] / 2),
        "color": color or "#999999",
        "kind": kind,
        "hp": hp_val,
        "maxHp": hp_val,
        "ownerId": None,
        "isNpc": True,
    }
    _state["tokens"][token_id] = token
    _state["turnOrder"].append(token_id)
    _push_log("system", f"DM spawned {token['name']}.")
    await _save()
    return token


async def remove_token(token_id: str):
    _state["tokens"].pop(token_id, None)
    _state["turnOrder"] = [t for t in _state["turnOrder"] if t != token_id]
    if _state["currentTurn"] >= len(_state["turnOrder"]):
        _state["currentTurn"] = -1
    await _save()


async def set_hp(token_id: str, hp: int):
    token = _state["tokens"].get(token_id)
    if not token:
        return None
    # Whether healing may overshoot is the ruleset's call, not this
    # function's; min_hp likewise, which is 0 in demo and death's door
    # in a ruleset that has one.
    ceiling = token["maxHp"] if RULES.healing_caps_at_max else hp
    token["hp"] = max(RULES.min_hp, min(ceiling, hp))
    await _save()
    return token


async def advance_turn():
    if not _state["turnOrder"]:
        return None
    _state["currentTurn"] = (_state["currentTurn"] + 1) % len(_state["turnOrder"])
    tok = _state["tokens"].get(current_turn_token_id())
    _push_log("system", f"Turn: {tok['name'] if tok else '?'}.")
    await _save()
    return tok


async def append_chat(who: str, text: str):
    text = str(text or "")[:500]
    if not text.strip():
        return
    _push_log(who, text)
    await _save()


async def append_roll_log(who: str, notation: str, result):
    if not result:
        _push_log(who, f'tried to roll "{notation}" — invalid notation.')
    else:
        mod_str = ""
        if result["mod"]:
            mod_str = f' +{result["mod"]}' if result["mod"] > 0 else f' {result["mod"]}'
        rolls_str = ", ".join(str(r) for r in result["rolls"])
        _push_log(who, f'rolled {result["notation"]}: [{rolls_str}]{mod_str} = {result["total"]}')
    await _save()
