"""HTTP endpoints and button actions, with no model behind them."""
import pytest
from fastapi.testclient import TestClient

from dungeon import config, live, state


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path)
    import server
    server.hub = live.Hub(live_models=[])
    return TestClient(server.app), server


def test_new_save_load(client):
    c, server = client
    r = c.post("/api/new", json={"name": "  Ash   Vale "}).json()
    assert r["state"]["player"]["name"] == "Ash Vale"
    sid = r["session_id"]
    assert c.get(f"/api/state/{sid}").json()["location"]["name"] == "Emberfall Square"
    assert c.post("/api/save", json={"session_id": sid, "slot": "first"}).json() == {"slot": "first"}
    assert c.get("/api/saves").json()[0]["name"] == "Ash Vale"
    loaded = c.post("/api/load", json={"slot": "first"}).json()
    assert loaded["session_id"] != sid
    assert c.post("/api/load", json={"slot": "nope"}).status_code == 404
    assert c.get("/api/state/unknown").status_code == 404


async def test_button_actions_update_adk_session():
    hub = live.Hub(live_models=[])
    g = state.new_game("Wren", seed=5)
    g["meta"]["location_id"] = "ashwood_edge"
    sid = await hub.create(g)

    def start(g, d):
        from dungeon import combat
        combat.start_combat(g, [{"template": "ash_wolf"}], d)
    await hub.apply(sid, start)
    lines, after = await hub.apply(sid, lambda g, d: live.button_action(g, d, {"action": "defend"}))
    assert any("guard" in line for line in lines)
    session = await hub.session_service.get_session(app_name=config.APP_NAME, user_id=live.USER, session_id=sid)
    assert session.state["combat"]["log"] == after["combat"]["log"]
    assert session.events[-1].author == "engine"
    assert session.events[-1].actions.state_delta


async def test_button_errors_become_notices():
    hub = live.Hub(live_models=[])
    sid = await hub.create(state.new_game("Wren", seed=1))
    sent = []

    async def send(msg):
        sent.append(msg)
    session = live.GameSession(hub, sid, send)
    await session.action({"action": "attack"})
    assert sent[-1]["type"] == "notice" and "aren't in a fight" in sent[-1]["text"]


async def test_live_events_become_tokens():
    from google.adk.events import Event
    from google.genai import types
    hub = live.Hub(live_models=[])
    sid = await hub.create(state.new_game("Wren", seed=1))
    sent = []

    async def send(msg):
        sent.append(msg)
    session = live.GameSession(hub, sid, send)
    await session._on_event(Event(author="game_master", partial=True,
                                  output_transcription=types.Transcription(text="Ash falls ")))
    await session._on_event(Event(author="game_master", partial=False,
                                  output_transcription=types.Transcription(text="Ash falls softly.", finished=True)))
    await session._on_event(Event(author="game_master", content=types.Content(role="model", parts=[
        types.Part(inline_data=types.Blob(data=b"\x00\x01", mime_type="audio/pcm;rate=24000"))])))
    await session._on_event(Event(author="game_master", turn_complete=True))
    assert sent[0] == {"type": "token", "text": "Ash falls ", "author": "game_master"}
    assert sent[1]["type"] == "final"
    assert sent[2] == b"\x00\x01"
    assert sent[3] == {"type": "turn_complete"}


async def test_button_reaches_a_running_live_session():
    hub = live.Hub(live_models=[])
    g = state.new_game("Wren", seed=5)
    g["meta"]["location_id"] = "ashwood_edge"
    sid = await hub.create(g)
    # what a running live invocation would be holding
    live_copy = await hub.session_service.get_session(app_name=config.APP_NAME, user_id=live.USER, session_id=sid)
    hub.plugin.sessions[sid] = [live_copy]

    def start(g, d):
        from dungeon import combat
        combat.start_combat(g, [{"template": "ash_wolf"}], d)
    await hub.apply(sid, start)
    await hub.apply(sid, lambda g, d: live.button_action(g, d, {"action": "attack"}))
    stored = await hub.game(sid)
    assert live_copy.state["combat"] == stored["combat"]
    assert live_copy.state["meta"]["rng"] == stored["meta"]["rng"]
    texts = [e["text"] for e in stored["combat"]["log"]]
    assert len(texts) == len(set(texts))
