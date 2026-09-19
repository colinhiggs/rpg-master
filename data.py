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

import copy
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
    # What game this is, for the client: the pools to draw, their
    # labels, and which one takes a creature out of the fight. It is
    # rebuilt from the binding on every start and never restored from
    # the save, the same way `players` is not — a saved description of
    # a ruleset you might since have changed is worse than none.
    "ruleset": RULES.as_json(),
    "players": {},   # sid -> { id, name, role, tokenId }  — NOT persisted, see load()
    "tokens": {},    # tokenId -> { id, name, x, y, color, kind, attributes, pools, characterId, ownerId, isNpc }
    # Characters are stored apart from tokens on purpose: a character
    # outlives the fight it was on the map for, one player may have
    # several, and a character that is not in this fight still exists.
    # A token that names one has no pools or attributes of its own —
    # see _sheet() — so there is one set of current values rather than
    # two that drift apart.
    "characters": {},  # characterId -> the sheet, see ruleset.fresh_character
    "turnOrder": [],
    "currentTurn": -1,
    "log": [],
}
_next_token_id = 1
_next_character_id = 1


def snapshot() -> dict:
    """The full state, exactly as broadcast to clients. Cheap: it's just
    the dict socket.io was already going to serialize to JSON."""
    return _state


def _migrate_token(token: dict) -> dict:
    """Bring a token saved before pools existed up to the current shape.

    A token used to carry `hp` and `maxHp`. The old value goes into
    whichever pool the ruleset says a creature goes down on, because
    that is what a single hit point total was standing in for; every
    other pool starts empty for the table to fill in. Switching ruleset
    between runs makes the old numbers meaningless anyway, which is why
    this is a courtesy rather than a migration worth versioning."""
    token.setdefault("characterId", None)
    if "attributes" not in token:
        token["attributes"] = RULES.fresh_attributes()
    if "pools" in token:
        return token
    old = token.pop("maxHp", None)
    current = token.pop("hp", old)
    vital = RULES.vital_pool
    supplied = {vital.name: old} if vital is not None and old is not None else {}
    token["pools"] = RULES.fresh_pools(supplied)
    if vital is not None and current is not None and vital.name in token["pools"]:
        token["pools"][vital.name]["current"] = int(current)
    return token


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
    global _state, _next_token_id, _next_character_id
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT data, next_token_id FROM game_state WHERE id = 1") as cur:
            row = await cur.fetchone()
    if row:
        saved = json.loads(row[0])
        _state["gridSize"] = saved.get("gridSize", RULES.grid_size)
        _state["tokens"] = {tid: _migrate_token(t)
                            for tid, t in saved.get("tokens", {}).items()}
        _state["turnOrder"] = saved.get("turnOrder", [])
        _state["currentTurn"] = saved.get("currentTurn", -1)
        _state["log"] = saved.get("log", [])
        _state["characters"] = {
            cid: _refresh_character(c)
            for cid, c in saved.get("characters", {}).items()
        }
        _state["players"] = {}  # always fresh — see docstring above
        _next_token_id = row[1]
        _next_character_id = saved.get("_nextCharacterId", 1)
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
            (json.dumps({**_state, "_nextCharacterId": _next_character_id}),
             _next_token_id, int(time.time())),
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


def _next_character_id_str() -> str:
    global _next_character_id
    cid = f"c{_next_character_id}"
    _next_character_id += 1
    return cid


def _sheet(token):
    """Where a token's pools and attributes actually live.

    A token linked to a character keeps none of its own: the character
    is the record and the token is its presence on the map, so damage
    taken in a fight is damage to the character and is still there next
    session. An unlinked token — most monsters — carries its own."""
    if token is None:
        return None
    char_id = token.get("characterId")
    if char_id:
        return _state["characters"].get(char_id) or token
    return token


def _refresh_character(char):
    """Recompute what the views show. Derived, cheap, and stored on the
    character so that it travels with it rather than being worked out
    again by everything that displays one."""
    char["warnings"] = RULES.check_character(char)
    char["totals"] = RULES.character_totals(char)
    return char


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
async def add_player(sid: str, name: str, role: str, pools=None,
                     attributes=None):
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
            "attributes": RULES.fresh_attributes(attributes),
            "pools": RULES.fresh_pools(pools, attributes),
            "characterId": None,
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


async def spawn_token(name: str, color: str, pools, x, y, kind: str = "goblin",
                      attributes=None):
    token_id = _next_token_id_str()
    if kind not in MODEL_KINDS:
        kind = "goblin"
    token = {
        "id": token_id,
        "name": str(name or "Monster")[:24],
        "x": _clamp_to_grid(x if x is not None else _state["gridSize"] / 2),
        "y": _clamp_to_grid(y if y is not None else _state["gridSize"] / 2),
        "color": color or "#999999",
        "kind": kind,
        "attributes": RULES.fresh_attributes(attributes),
        "pools": RULES.fresh_pools(pools, attributes),
        "characterId": None,
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


async def set_pool(token_id: str, pool_name: str, value: int):
    """Set one pool's current value. Whether it may exceed the maximum,
    and what it clamps to from below, are the pool's own business — see
    ruleset.py, where Ico's core hit points deliberately have no floor
    because they run past zero to a limit this server cannot compute."""
    token = _state["tokens"].get(token_id)
    pool = RULES.pools_by_name.get(pool_name)
    if not token or pool is None:
        return None
    block = _sheet(token)["pools"].get(pool_name)
    if block is None:
        return None
    block["current"] = pool.clamp(int(value), block["max"])
    await _save()
    return token


async def set_pool_max(token_id: str, pool_name: str, value):
    """Set one pool's maximum, or hand it back to the book.

    A maximum the ruleset derives follows its attribute until somebody
    overrides it here, and then it stops — which is right, because the
    pools Ico derives are stated as a *base* that advancement widens,
    so a character who has spent points has a maximum the formula is
    only the floor of. `value` of None reverts to the derived figure."""
    token = _state["tokens"].get(token_id)
    pool = RULES.pools_by_name.get(pool_name)
    if not token or pool is None:
        return None
    sheet = _sheet(token)
    block = sheet["pools"].get(pool_name)
    if block is None:
        return None
    if value is None:
        if pool.derives_from is None:
            return None
        block["derived"] = True
        block["max"] = pool.max_for(sheet.get("attributes"))
    else:
        block["max"] = max(0, int(value))
        block["derived"] = False
    block["current"] = pool.clamp(block["current"], block["max"])
    await _save()
    return token


# ---------------------------------------------------------------------
# Characters. Stored apart from tokens; see _sheet() for why.
# ---------------------------------------------------------------------
async def create_character(name=None, attributes=None, equipment=None):
    if RULES.character is None:
        return None            # this ruleset has no character rules
    char_id = _next_character_id_str()
    char = RULES.fresh_character(name, attributes, equipment)
    char["id"] = char_id
    _state["characters"][char_id] = _refresh_character(char)
    _push_log("system", f"{char['name']} was written up.")
    await _save()
    return char


async def update_character(char_id: str, changes: dict):
    """Apply a partial update. Only the fields a character actually has
    are taken, so a client cannot invent one; and changing attributes
    moves the pools that derive from them, exactly as it does on a
    token."""
    char = _state["characters"].get(char_id)
    if not char or not isinstance(changes, dict):
        return None
    if "name" in changes:
        char["name"] = str(changes["name"] or "")[:48] or char["name"]
    if "notes" in changes:
        char["notes"] = str(changes["notes"] or "")[:4000]
    if isinstance(changes.get("attributes"), dict):
        for attr, value in changes["attributes"].items():
            if attr in RULES.attributes:
                try:
                    char["attributes"][attr] = int(value)
                except (TypeError, ValueError):
                    pass
        RULES.recompute_pools(char)
    if isinstance(changes.get("equipment"), dict):
        for slot in ("wielded", "worn", "carried"):
            if slot in changes["equipment"]:
                char["equipment"][slot] = [
                    str(i) for i in (changes["equipment"][slot] or [])
                ]
    for free_form in ("skills", "disciplines"):
        if isinstance(changes.get(free_form), dict):
            char[free_form] = {str(k): v for k, v in changes[free_form].items()}
    if isinstance(changes.get("powers"), list):
        char["powers"] = [str(p) for p in changes["powers"]]
    _refresh_character(char)
    await _save()
    return char


async def delete_character(char_id: str):
    char = _state["characters"].pop(char_id, None)
    if char is None:
        return None
    for token in _state["tokens"].values():
        if token.get("characterId") == char_id:
            # The token keeps the numbers it was playing with rather
            # than blanking: the sheet is gone, the creature is still
            # standing on the map.
            token["characterId"] = None
            token.setdefault("attributes", dict(char.get("attributes") or {}))
            token.setdefault("pools", copy.deepcopy(char.get("pools") or {}))
    _push_log("system", f"{char['name']}'s sheet was deleted.")
    await _save()
    return char


async def assign_character(token_id: str, char_id):
    """Point a token at a character, or at nothing.

    From here on the token has no pools of its own — _sheet() sends
    every read and write to the character — so a wound taken in this
    fight is on the sheet next session."""
    token = _state["tokens"].get(token_id)
    if not token:
        return None
    if char_id in (None, ""):
        char = _state["characters"].get(token.get("characterId"))
        token["characterId"] = None
        if char is not None:
            token["attributes"] = dict(char.get("attributes") or {})
            token["pools"] = copy.deepcopy(char.get("pools") or {})
        await _save()
        return token
    if char_id not in _state["characters"]:
        return None
    token["characterId"] = char_id
    token.pop("pools", None)
    token.pop("attributes", None)
    _push_log("system", f"{token['name']} is now "
                        f"{_state['characters'][char_id]['name']}.")
    await _save()
    return token


async def set_attribute(token_id: str, attr: str, value: int):
    """Set one attribute, and move whatever hangs off it.

    This is the rung the server just climbed: a number the table used to
    type into four boxes is typed into one, and the pools the book
    derives from it follow. A pool somebody has overridden does not,
    deliberately."""
    token = _state["tokens"].get(token_id)
    if not token or attr not in RULES.attributes:
        return None
    sheet = _sheet(token)
    sheet.setdefault("attributes", RULES.fresh_attributes())
    sheet["attributes"][attr] = int(value)
    RULES.recompute_pools(sheet)
    if sheet is not token:
        _refresh_character(sheet)
    await _save()
    return token


async def apply_damage(token_id: str, amount: int):
    """Take `amount` off the token, through the pools in the order the
    RULESET declares — `hit-points.damage_order` in Ico, which is
    mastery before core. The order is read rather than written here:
    the server executes a sequence the book states, which is the whole
    difference between this and implementing a damage rule."""
    token = _state["tokens"].get(token_id)
    if not token or amount is None:
        return None
    left = int(amount)
    if left < 0:
        return await heal(token_id, -left)
    for pool_name in RULES.damage_order:
        if left <= 0:
            break
        block = _sheet(token)["pools"].get(pool_name)
        pool = RULES.pools_by_name.get(pool_name)
        if block is None or pool is None:
            continue
        if pool.floor is None:
            # Nothing stops this pool absorbing the rest: Ico's core hit
            # points run past zero and the limit is not the server's to
            # know.
            available = left
        else:
            available = max(0, block["current"] - pool.floor)
        taken = min(left, available)
        block["current"] = pool.clamp(block["current"] - taken, block["max"])
        left -= taken
    await _save()
    return token


async def heal(token_id: str, amount: int):
    """Healing runs the damage order backwards, so the pool that took
    the damage last is the one that comes back first."""
    token = _state["tokens"].get(token_id)
    if not token or amount is None:
        return None
    left = int(amount)
    for pool_name in reversed(RULES.damage_order):
        if left <= 0:
            break
        block = _sheet(token)["pools"].get(pool_name)
        pool = RULES.pools_by_name.get(pool_name)
        if block is None or pool is None:
            continue
        room = block["max"] - block["current"] if pool.caps_at_max else left
        given = min(left, max(0, room))
        block["current"] = pool.clamp(block["current"] + given, block["max"])
        left -= given
    await _save()
    return token


def is_down(token) -> bool:
    """Whether a creature is out of the fight, by the ruleset's own
    threshold rather than by hit points reaching zero."""
    return RULES.is_down(_sheet(token))


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
