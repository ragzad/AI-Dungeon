"""Story premises: the Creator's opening is checked, used and kept in saves."""
import json

import pytest
from fastapi.testclient import TestClient

from dungeon import agents, combat, config, live, premise, state, world
from dungeon.state import GameError

from conftest import FakeToolContext

OPENING = {
    "setting_name": "Skyreach",
    "tone": "tense, glittering, wind-blown",
    "blurb": "A city held aloft by failing engines. The Guild owns the vault and everybody owes the Guild.",
    "start": {"name": "Cloudside Docks", "description": "Airships creak at their moorings while the wind howls.",
              "features": [{"name": "Mooring Post", "description": "Frayed rope and a scratched sigil."}],
              "items": ["lantern", "not_an_item"]},
    "places": [
        {"direction": "north", "name": "The Brass Kettle", "description": "A smoky tavern full of pilots.",
         "features": [], "items": [], "encounter": [], "encounter_text": "", "rest": True},
        {"direction": "east", "name": "Guild Vault Steps", "description": "Marble steps under watchful eyes.",
         "features": [], "items": ["ember_shard"],
         "encounter": [{"template": "bandit", "name": "Guild Enforcer"}, {"template": "dragon", "name": "Nope"}],
         "encounter_text": "Two enforcers step out of the shadows.", "rest": False},
        {"direction": "north", "name": "Duplicate", "description": "Should be dropped.", "features": [],
         "items": [], "encounter": [], "encounter_text": "", "rest": False},
    ],
    "npcs": [
        {"name": "Vex Marlowe", "role": "fixer", "personality": "Sharp and impatient.", "voice": "Clipped.",
         "goals": ["Rob the vault"], "secret": "She used to work for the Guild.", "disposition": 30,
         "fights_as": "bandit", "where": "start", "sells": ["healing_potion", "silver_locket"]},
        {"name": "Old Tamsin", "role": "engine keeper", "personality": "Kind, tired.", "voice": "Soft.",
         "goals": ["Keep the city up"], "secret": "", "disposition": 60, "fights_as": "giant",
         "where": "north", "sells": []},
    ],
    "quest": {"title": "Crack the Vault", "desc": "Get past the Guild's enforcers.", "giver": "Vex Marlowe",
              "kind": "defeat", "monster": "bandit"},
    "unexplored": [{"direction": "south", "hint": "a rope bridge swaying into fog"}],
}


def test_clean_premise():
    assert premise.clean("   ") is None
    assert premise.clean("Surprise me") is None
    assert premise.clean("  a   haunted\nlighthouse ") == "a haunted lighthouse"
    assert len(premise.clean("x" * 1000)) == premise.MAX_PREMISE


def test_build_world_validates_the_opening():
    w, setting, _ = premise.build_world(json.loads(json.dumps(OPENING)))
    locs = w["locations"]
    start = locs["start"]
    assert start["name"] == "Cloudside Docks" and start["visited"]
    assert [i["id"] for i in start["items"]] == ["lantern"]
    assert set(start["exits"]) == {"north", "east", "south"}
    assert start["exits"]["south"] == {"to": None, "hint": "a rope bridge swaying into fog"}
    vault = locs[start["exits"]["east"]]
    assert vault["encounter"]["enemies"] == ["bandit"] and vault["encounter"]["names"] == ["Guild Enforcer"]
    assert locs[start["exits"]["north"]]["rest"]
    vex, tamsin = w["npcs"]["npc_vex_marlowe"], w["npcs"]["npc_old_tamsin"]
    assert vex["location_id"] == "start" and vex["trades"]["sells"] == ["healing_potion"]
    assert vex["disposition"] >= 45 and vex["quests"] == ["hook", "boss"]
    assert tamsin["combat"]["template"] == "bandit" and tamsin["location_id"] == start["exits"]["north"]
    assert w["quests"]["hook"]["goal"] == {"type": "defeat", "template": "bandit", "count": 1}
    assert setting["name"] == "Skyreach"


def test_quest_foe_is_placed_if_missing():
    spec = json.loads(json.dumps(OPENING))
    spec["places"][1]["encounter"] = []
    spec["quest"]["monster"] = "cinder_ghoul"
    w, _, _ = premise.build_world(spec)
    placed = [l for l in w["locations"].values() if l.get("encounter")]
    assert placed and placed[0]["encounter"]["enemies"] == ["cinder_ghoul"]


def test_find_quest_item_is_placed():
    spec = json.loads(json.dumps(OPENING))
    spec["quest"] = {"title": "The Ledger", "desc": "Find it.", "giver": "Old Tamsin", "kind": "find", "item": "bone_charm"}
    w, _, _ = premise.build_world(spec)
    assert w["quests"]["hook"]["goal"] == {"type": "deliver", "item": "bone_charm", "to": "npc_old_tamsin"}
    assert any(i["id"] == "bone_charm" for l in w["locations"].values() for i in l["items"])


@pytest.mark.parametrize("broken", ["start", "places", "npcs"])
def test_unusable_openings_are_refused(broken):
    spec = json.loads(json.dumps(OPENING))
    spec[broken] = {} if broken == "start" else []
    with pytest.raises(GameError):
        premise.build_world(spec)


def test_premise_game_plays_and_saves(tmp_path):
    g = premise.apply(state.new_game("Wren", seed=3), "a heist in a floating city", json.loads(json.dumps(OPENING)))
    assert state.public_view(g)["setting"] == {"name": "Skyreach", "premise": "a heist in a floating city"}
    assert not any(i["id"] == "old_map" for i in g["player"]["inventory"])
    d = state.dice(g)
    result = world.move(g, "east", d)
    assert g["mode"] == "combat" and "encounter" in result
    names = [c["name"] for cid, c in g["combat"]["combatants"].items() if cid != "player"]
    assert names == ["Guild Enforcer"]
    state.save_slot(tmp_path, "heist", g)
    back = state.load_slot(tmp_path, "heist")
    assert back["meta"]["setting"]["premise"] == "a heist in a floating city"
    assert back["world"]["locations"]["start"]["name"] == "Cloudside Docks"


def test_agents_get_the_setting():
    g = premise.apply(state.new_game("Wren", seed=3), "a heist in a floating city", json.loads(json.dumps(OPENING)))

    class Ctx:
        state = g
    text = agents.gm_instruction(Ctx())
    assert "Skyreach" in text and "a heist in a floating city" in text and "Emberfall" not in text

    class Plain:
        state = state.new_game("Wren", seed=1)
    assert "Emberfall" in agents.gm_instruction(Plain())


async def test_dialogue_and_creator_requests_carry_the_setting(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    g = premise.apply(state.new_game("Wren", seed=3), "a heist in a floating city", json.loads(json.dumps(OPENING)))
    seen = []

    class FakeTool:
        async def run_async(self, args, tool_context):
            seen.append(json.loads(args["request"]))
            return {"name": "x"}
    monkeypatch.setattr(agents, "dialogue_tool", FakeTool())
    monkeypatch.setattr(agents, "creator_tool", FakeTool())
    ctx = FakeToolContext(g)
    await agents.ask_dialogue(ctx, {"name": "Vex"}, "hello", None)
    await agents.ask_creator(ctx, "Cloudside Docks", "south", "a rope bridge")
    assert all("Skyreach" in r["setting"] for r in seen)


def test_opener_uses_the_premise():
    g = premise.apply(state.new_game("Wren", seed=3), "a heist in a floating city", json.loads(json.dumps(OPENING)))
    text = live.opener(g)
    assert "a heist in a floating city" in text and "Vex Marlowe" in text and "Emberfall" not in text


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path)
    import server
    server.hub = live.Hub(live_models=[])
    return TestClient(server.app), server


def test_new_game_with_premise(client, monkeypatch):
    c, server = client
    asked = []

    async def fake_opening(text):
        asked.append(text)
        return json.loads(json.dumps(OPENING))
    monkeypatch.setattr(server.hub, "opening", fake_opening)
    monkeypatch.setattr(config, "has_key", lambda: True)
    r = c.post("/api/new", json={"name": "Wren", "premise": "  A heist in a floating city "}).json()
    assert asked == ["A heist in a floating city"]
    assert r["notice"] is None
    assert r["state"]["location"]["name"] == "Cloudside Docks"
    assert r["state"]["setting"]["name"] == "Skyreach"
    sid = r["session_id"]
    c.post("/api/save", json={"session_id": sid, "slot": "heist"})
    loaded = c.post("/api/load", json={"slot": "heist"}).json()
    assert loaded["state"]["setting"]["premise"] == "A heist in a floating city"


def test_surprise_me_keeps_emberfall(client, monkeypatch):
    c, server = client

    async def boom(text):
        raise AssertionError("should not be called")
    monkeypatch.setattr(server.hub, "opening", boom)
    r = c.post("/api/new", json={"name": "Wren", "premise": "Surprise me"}).json()
    assert r["state"]["location"]["name"] == "Emberfall Square" and r["state"]["setting"]["premise"] is None


def test_failed_opening_falls_back(client, monkeypatch):
    c, server = client

    async def quota(text):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(server.hub, "opening", quota)
    monkeypatch.setattr(config, "has_key", lambda: True)
    r = c.post("/api/new", json={"name": "Wren", "premise": "a haunted lighthouse"}).json()
    assert r["state"]["location"]["name"] == "Emberfall Square"
    assert "Emberfall" in r["notice"]


async def test_hub_opening_parses_and_caches(monkeypatch, tmp_path):
    from google.adk.events import Event
    from google.genai import types
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    hub = live.Hub(live_models=[])
    calls = []

    async def fake_run(**kwargs):
        calls.append(kwargs)
        yield Event(author="creator_opening", content=types.Content(role="model", parts=[types.Part(text=json.dumps(OPENING))]))
    monkeypatch.setattr(hub.opening_runner, "run_async", fake_run)
    first = await hub.opening("a heist in a floating city")
    second = await hub.opening("A heist in a floating city")
    assert first["setting_name"] == second["setting_name"] == "Skyreach"
    assert len(calls) == 1


async def test_text_fallback_uses_premise_instruction():
    hub = live.Hub(live_models=[], text_model="gemini-test")
    agent = hub.runner("gemini-test", live=False).agent
    assert agent.instruction is agents.gm_instruction
