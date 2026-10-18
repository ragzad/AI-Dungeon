import asyncio
import json
import logging
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dungeon import config, state
from dungeon.live import GameSession, Hub, opener
from dungeon.state import GameError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("dungeon")

app = FastAPI(title="AI Dungeon")
hub = Hub()
STATIC = config.ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_fresh = set()  # sessions that haven't had their opening narration yet


class NewGame(BaseModel):
    name: str = "Wren"


class SaveRequest(BaseModel):
    session_id: str
    slot: str = "autosave"


class LoadRequest(BaseModel):
    slot: str


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "key": config.has_key(), "live_models": hub.live_models, "text_model": hub.text_model,
            "background_model": config.BACKGROUND_MODEL}


@app.post("/api/new")
async def new_game(body: NewGame):
    name = " ".join(body.name.split())[:24] or "Wren"
    g = state.new_game(name)
    g["world"]["locations"]["square"]["visited"] = True
    sid = await hub.create(g)
    _fresh.add((sid, False))
    return {"session_id": sid, "state": state.public_view(g)}


@app.get("/api/state/{sid}")
async def get_state(sid: str):
    try:
        return state.public_view(await hub.game(sid))
    except KeyError:
        raise HTTPException(404, "No such game. Start a new one or load a save.")


@app.post("/api/save")
async def save(body: SaveRequest):
    try:
        g = await hub.game(body.session_id)
        slot = state.save_slot(config.SAVE_DIR, body.slot, g)
    except KeyError:
        raise HTTPException(404, "No such game.")
    except GameError as exc:
        raise HTTPException(400, str(exc))
    return {"slot": slot}


@app.get("/api/saves")
async def saves():
    return state.list_slots(config.SAVE_DIR)


@app.post("/api/load")
async def load(body: LoadRequest):
    try:
        g = state.load_slot(config.SAVE_DIR, body.slot)
    except GameError as exc:
        raise HTTPException(404, str(exc))
    sid = await hub.create(g)
    _fresh.add((sid, True))
    return {"session_id": sid, "state": state.public_view(g)}


@app.websocket("/ws/{sid}")
async def ws_game(ws: WebSocket, sid: str):
    await ws.accept()
    try:
        g = await hub.game(sid)
    except KeyError:
        await ws.send_json({"type": "notice", "level": "error", "text": "That game has expired. Start a new one or load a save."})
        await ws.close()
        return
    lock = asyncio.Lock()

    async def send(msg):
        async with lock:
            try:
                if isinstance(msg, (bytes, bytearray)):
                    await ws.send_bytes(bytes(msg))
                else:
                    await ws.send_json(msg)
            except Exception:
                pass

    first = None
    for loaded in (False, True):
        if (sid, loaded) in _fresh:
            _fresh.discard((sid, loaded))
            first = opener(g, loaded)
    session = GameSession(hub, sid, send)
    hub.games[sid] = session
    await session.push_state()
    await session.start(first)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await session.send_audio(msg["bytes"])
                continue
            data = json.loads(msg.get("text") or "{}")
            kind = data.get("type")
            if kind == "text":
                await send({"type": "echo", "text": data.get("text", "")})
                await session.send_text(data.get("text", ""))
            elif kind == "action":
                await session.action(data)
            elif kind == "ping":
                await send({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
        if hub.games.get(sid) is session:
            hub.games.pop(sid, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8010")))
