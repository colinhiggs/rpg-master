# server.py — Single-room RPG server (prototype), Python port.
#
# Same event contract as the Node/Socket.io version. All state mutation
# and persistence lives in data.py — this file's job is just: is this
# sid allowed to do what it's asking, and if so, apply it and tell
# everyone. Splitting it this way is what makes a later move to a full
# relational schema a change to data.py, not to every handler here.
#
# Stack: FastAPI (serves the static client) + python-socketio (Socket.io
# protocol, ASGI mode) + Uvicorn (ASGI server) + SQLite (via data.py).

from pathlib import Path

import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import data

PUBLIC_DIR = Path(__file__).parent / "public"

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

fastapi_app = FastAPI()
fastapi_app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="public")

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)


async def broadcast_state():
    await sio.emit("state", data.snapshot())


def _may_edit(sid, token):
    """A player may change their own token; the DM may change anything.
    The same check three handlers were making inline before there were
    three of them."""
    player = data.get_player(sid)
    if not player or not token:
        return False
    return player["role"] == "dm" or token["ownerId"] == sid


@sio.event
async def connect(sid, environ):
    pass  # nothing to do until the client sends "join"


@sio.event
async def join(sid, payload):
    payload = payload or {}
    # `pools` is whatever the player typed for the tracks the ruleset
    # cannot state a starting value for — in Ico that is all four of
    # them, because every one derives from a character sheet the server
    # does not hold. Absent, they come up as zero for filling in later.
    await data.add_player(sid, payload.get("name"), payload.get("role"),
                          payload.get("pools"), payload.get("attributes"))
    player = data.get_player(sid)
    await sio.emit("joined", {"selfId": sid, "tokenId": player["tokenId"]}, to=sid)
    await broadcast_state()


@sio.event
async def moveToken(sid, payload):
    payload = payload or {}
    token = data.get_token(payload.get("tokenId"))
    # Players may only move their own token; the DM may move anything.
    if not _may_edit(sid, token):
        return
    await data.move_token(token["id"], payload.get("x", token["x"]), payload.get("y", token["y"]))
    await broadcast_state()


@sio.event
async def spawnToken(sid, payload):
    payload = payload or {}
    player = data.get_player(sid)
    if not player or player["role"] != "dm":
        return
    await data.spawn_token(
        payload.get("name"), payload.get("color"), payload.get("pools"),
        payload.get("x"), payload.get("y"), payload.get("kind", "goblin"),
        payload.get("attributes"),
    )
    await broadcast_state()


@sio.event
async def removeToken(sid, payload):
    payload = payload or {}
    player = data.get_player(sid)
    if not player or player["role"] != "dm":
        return
    await data.remove_token(payload.get("tokenId"))
    await broadcast_state()


@sio.event
async def setPool(sid, payload):
    """Set one pool's current value outright."""
    payload = payload or {}
    token = data.get_token(payload.get("tokenId"))
    if not _may_edit(sid, token):
        return
    try:
        value = int(payload.get("value"))
    except (TypeError, ValueError):
        return
    await data.set_pool(token["id"], payload.get("pool"), value)
    await broadcast_state()


@sio.event
async def setPoolMax(sid, payload):
    """Set one pool's maximum — the table filling in the numbers the
    ruleset derives from a character sheet this server has not got."""
    payload = payload or {}
    token = data.get_token(payload.get("tokenId"))
    if not _may_edit(sid, token):
        return
    raw = payload.get("value")
    if raw is None or raw == "":
        value = None            # hand it back to the book's derivation
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return
    await data.set_pool_max(token["id"], payload.get("pool"), value)
    await broadcast_state()


@sio.event
async def setAttribute(sid, payload):
    """Set one of a creature's attributes. Every pool the ruleset
    derives from it moves with it, unless the table has overridden that
    pool."""
    payload = payload or {}
    token = data.get_token(payload.get("tokenId"))
    if not _may_edit(sid, token):
        return
    try:
        value = int(payload.get("value"))
    except (TypeError, ValueError):
        return
    await data.set_attribute(token["id"], payload.get("attr"), value)
    await broadcast_state()


@sio.event
async def damage(sid, payload):
    """Take damage off a token through the ruleset's own damage order,
    rather than making whoever is at the keyboard work out which pool
    it comes off. A negative amount heals, in reverse order."""
    payload = payload or {}
    token = data.get_token(payload.get("tokenId"))
    if not _may_edit(sid, token):
        return
    try:
        amount = int(payload.get("amount"))
    except (TypeError, ValueError):
        return
    await data.apply_damage(token["id"], amount)
    await broadcast_state()


@sio.event
async def nextTurn(sid, payload=None):
    player = data.get_player(sid)
    if not player or player["role"] != "dm":
        return
    await data.advance_turn()
    await broadcast_state()


@sio.event
async def rollDice(sid, notation):
    player = data.get_player(sid)
    if not player:
        return
    result = data.roll_dice(str(notation or data.RULES.default_roll))
    await data.append_roll_log(player["name"], notation, result)
    await broadcast_state()


@sio.event
async def chat(sid, text):
    player = data.get_player(sid)
    if not player:
        return
    await data.append_chat(player["name"], text)
    await broadcast_state()


# ---------------------------------------------------------------------
# Characters. The DM may write up and edit anybody; a player may edit a
# character their own token is playing. Nobody may delete somebody
# else's, and only the DM may point a token at a sheet — that is a
# decision about whose character is in the fight.
# ---------------------------------------------------------------------
def _is_dm(sid):
    player = data.get_player(sid)
    return bool(player) and player["role"] == "dm"


def _may_edit_character(sid, char_id):
    if _is_dm(sid):
        return True
    player = data.get_player(sid)
    if not player:
        return False
    token = data.get_token(player.get("tokenId"))
    return bool(token) and token.get("characterId") == char_id


@sio.event
async def createCharacter(sid, payload):
    payload = payload or {}
    player = data.get_player(sid)
    if not player:
        return
    char = await data.create_character(payload.get("name"),
                                       payload.get("attributes"),
                                       payload.get("equipment"))
    if char is None:
        # No character rules in this ruleset — say so rather than
        # leaving the client waiting for a sheet that is not coming.
        await sio.emit("characterRefused", {
            "reason": f"the '{data.RULES.name}' ruleset has no character "
                      "creation this server knows about",
        }, to=sid)
        return
    # A player writing themselves up gets their own token pointed at it.
    if not _is_dm(sid) and player.get("tokenId"):
        await data.assign_character(player["tokenId"], char["id"])
    await sio.emit("characterCreated", {"id": char["id"]}, to=sid)
    await broadcast_state()


@sio.event
async def updateCharacter(sid, payload):
    payload = payload or {}
    char_id = payload.get("id")
    if not _may_edit_character(sid, char_id):
        return
    await data.update_character(char_id, payload.get("changes") or {})
    await broadcast_state()


@sio.event
async def deleteCharacter(sid, payload):
    payload = payload or {}
    if not _is_dm(sid):
        return
    await data.delete_character(payload.get("id"))
    await broadcast_state()


@sio.event
async def assignCharacter(sid, payload):
    payload = payload or {}
    if not _is_dm(sid):
        return
    await data.assign_character(payload.get("tokenId"), payload.get("characterId"))
    await broadcast_state()


@sio.event
async def disconnect(sid):
    player = await data.remove_player(sid)
    if player:
        await broadcast_state()


@fastapi_app.on_event("startup")
async def on_startup():
    # Print where every game number came from. A value the book does
    # not state and the table supplied instead should be visible in the
    # log rather than assumed — see ruleset.py.
    print(data.RULES.provenance(), flush=True)
    await data.load()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3000)
