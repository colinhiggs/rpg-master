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


@sio.event
async def connect(sid, environ):
    pass  # nothing to do until the client sends "join"


@sio.event
async def join(sid, payload):
    payload = payload or {}
    await data.add_player(sid, payload.get("name"), payload.get("role"))
    player = data.get_player(sid)
    await sio.emit("joined", {"selfId": sid, "tokenId": player["tokenId"]}, to=sid)
    await broadcast_state()


@sio.event
async def moveToken(sid, payload):
    payload = payload or {}
    player = data.get_player(sid)
    token = data.get_token(payload.get("tokenId"))
    if not player or not token:
        return
    # Players may only move their own token; the DM may move anything.
    if player["role"] != "dm" and token["ownerId"] != sid:
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
        payload.get("name"), payload.get("color"), payload.get("hp"),
        payload.get("x"), payload.get("y"), payload.get("kind", "goblin"),
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
async def setHp(sid, payload):
    payload = payload or {}
    player = data.get_player(sid)
    token = data.get_token(payload.get("tokenId"))
    if not player or not token:
        return
    if player["role"] != "dm" and token["ownerId"] != sid:
        return
    try:
        hp = int(payload.get("hp"))
    except (TypeError, ValueError):
        return
    await data.set_hp(token["id"], hp)
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
    result = data.roll_dice(str(notation or "d20"))
    await data.append_roll_log(player["name"], notation, result)
    await broadcast_state()


@sio.event
async def chat(sid, text):
    player = data.get_player(sid)
    if not player:
        return
    await data.append_chat(player["name"], text)
    await broadcast_state()


@sio.event
async def disconnect(sid):
    player = await data.remove_player(sid)
    if player:
        await broadcast_state()


@fastapi_app.on_event("startup")
async def on_startup():
    await data.load()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3000)
