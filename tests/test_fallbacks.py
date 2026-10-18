"""Quota handling: background agents fall back to another model, the Game
Master falls back from Live to text."""
from types import SimpleNamespace

from dungeon import config, live, plugins, state


class Quota(Exception):
    code = 429


async def test_plugin_ignores_other_errors():
    p = plugins.GamePlugin()
    req = SimpleNamespace(model=config.BACKGROUND_MODEL)
    assert await p.on_model_error_callback(callback_context=None, llm_request=req, error=ValueError("x")) is None


async def test_plugin_retries_on_fallback_model(monkeypatch):
    seen = {}

    class FakeGemini:
        def __init__(self, model):
            seen["model"] = model

        async def generate_content_async(self, request, stream=False):
            yield "fallback answer"
    monkeypatch.setattr(plugins, "Gemini", FakeGemini)
    p = plugins.GamePlugin()
    req = SimpleNamespace(model=config.BACKGROUND_MODEL)
    out = await p.on_model_error_callback(callback_context=None, llm_request=req, error=Quota("429"))
    assert out == "fallback answer"
    assert seen["model"] == config.BACKGROUND_FALLBACK and req.model == config.BACKGROUND_FALLBACK


def test_quota_detection():
    assert plugins.is_quota_error(Quota())
    assert plugins.is_quota_error(RuntimeError("RESOURCE_EXHAUSTED: slow down"))
    assert not plugins.is_quota_error(RuntimeError("bad request"))


async def test_no_live_model_means_text_mode():
    hub = live.Hub(live_models=[])
    sid = await hub.create(state.new_game("Wren", seed=1))
    sent = []

    async def send(msg):
        sent.append(msg)
    session = live.GameSession(hub, sid, send)
    turns = []

    async def fake_turn(text):
        turns.append(text)
    session._text_turn = fake_turn
    await session.start(None)
    assert session.mode == "text"
    assert {"type": "status", "engine": "text", "model": hub.text_model} in sent
    await session.send_text("look around")
    import asyncio
    await asyncio.sleep(0)
    assert turns == ["look around"]


async def test_live_quota_falls_through_to_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    hub = live.Hub(live_models=["live-a", "live-b"])
    sid = await hub.create(state.new_game("Wren", seed=1))
    tried = []

    class FailingRunner:
        def __init__(self, model):
            self.model = model

        async def run_live(self, **kw):
            tried.append(self.model)
            raise Quota("429 RESOURCE_EXHAUSTED")
            yield  # pragma: no cover
    hub.runner = lambda model, live: FailingRunner(model)
    sent = []

    async def send(msg):
        sent.append(msg)
    session = live.GameSession(hub, sid, send)
    texts = []

    async def fake_turn(text):
        texts.append(text)
    session._text_turn = fake_turn
    await session.start("[start] hello")
    await session.task
    assert tried == ["live-a", "live-b"]
    assert session.mode == "text"
    assert any(m.get("type") == "notice" and "text" in m["text"] for m in sent if isinstance(m, dict))
    import asyncio
    await asyncio.sleep(0)
    assert texts == ["[start] hello"]
