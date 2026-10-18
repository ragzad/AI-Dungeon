"""The passcode gate: off by default, and when on, the page, API and WebSocket all need it."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from dungeon import access, config, live


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path)
    monkeypatch.setattr(access, "_fails", {})
    import server
    server.hub = live.Hub(live_models=[])
    return TestClient(server.app), server


def test_no_code_means_no_gate(client):
    c, _ = client
    assert "AI Dungeon" in c.get("/").text and "passcode" not in c.get("/").text
    assert c.post("/api/new", json={"name": "Wren"}).status_code == 200


def test_gate_blocks_page_api_and_websocket(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "ember-otter-lantern")
    c, _ = client
    page = c.get("/")
    assert page.status_code == 200 and "Enter the passcode" in page.text and "app.js" not in page.text
    assert c.get("/static/app.js").status_code == 401
    assert c.post("/api/new", json={"name": "Wren"}).status_code == 401
    assert c.get("/api/saves").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/anything") as ws:
            ws.receive_json()


def test_open_paths_stay_open(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "ember-otter-lantern")
    c, _ = client
    assert c.get("/api/health").json()["ok"]
    m = c.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone"
    assert all(c.get(i["src"]).status_code == 200 for i in m.json()["icons"])
    assert c.get("/sw.js").status_code == 200


def test_right_code_sets_a_cookie_and_lets_you_in(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "ember-otter-lantern")
    c, _ = client
    assert c.post("/api/login", json={"code": "wrong"}).status_code == 401
    r = c.post("/api/login", json={"code": "  Ember-Otter-Lantern "})
    assert r.status_code == 200
    cookie = r.cookies.get(access.COOKIE)
    assert cookie and "ember" not in cookie  # a hash, not the code
    assert "app.js" in c.get("/").text
    sid = c.post("/api/new", json={"name": "Wren"}).json()["session_id"]
    assert c.get(f"/api/state/{sid}").status_code == 200


def test_too_many_wrong_guesses_lock_you_out(client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "ember-otter-lantern")
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    c, _ = client
    for _ in range(access.MAX_FAILS):
        assert c.post("/api/login", json={"code": "guess"}, headers={"cf-connecting-ip": "1.2.3.4"}).status_code == 401
    assert c.post("/api/login", json={"code": "ember-otter-lantern"}, headers={"cf-connecting-ip": "1.2.3.4"}).status_code == 429
    # someone else isn't punished for it
    assert c.post("/api/login", json={"code": "ember-otter-lantern"}, headers={"cf-connecting-ip": "5.6.7.8"}).status_code == 200


async def _no_sleep(*a, **k):
    return None


def test_changing_the_code_logs_everyone_out(monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "one")
    old = access.token()
    monkeypatch.setenv("ACCESS_CODE", "two")
    assert not access.allowed({access.COOKIE: old})
