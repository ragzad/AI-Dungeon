"""What the Game Master is told: new or loaded game, NPC lines word for word, and the real fight."""
import pytest
from fastapi.testclient import TestClient

from dungeon import agents, combat, config, live, state, tools

from conftest import FakeToolContext


class Ctx:
    def __init__(self, g):
        self.state = g


def test_instruction_says_new_or_loaded():
    g = state.new_game("Wren", seed=1)
    assert agents.SESSION_NEW in agents.gm_instruction(Ctx(g))
    g["meta"]["origin"] = "loaded"
    text = agents.gm_instruction(Ctx(g))
    assert agents.SESSION_LOADED in text and agents.SESSION_NEW not in text
    assert "SESSION" not in text and "[start new]" in text


def test_openers_are_explicit():
    g = state.new_game("Wren", seed=1)
    new = live.opener(g)
    assert new.startswith("[start new]") and "never been here" in new and "welcome back" in new.lower()
    loaded = live.opener(g, loaded=True)
    assert loaded.startswith("[start loaded]") and "Welcome them back" in loaded


def test_loading_marks_the_game_as_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path)
    import server
    server.hub = live.Hub(live_models=[])
    c = TestClient(server.app)
    sid = c.post("/api/new", json={"name": "Wren"}).json()["session_id"]
    import asyncio
    assert asyncio.run(server.hub.game(sid))["meta"]["origin"] == "new"
    c.post("/api/save", json={"session_id": sid, "slot": "s"})
    sid2 = c.post("/api/load", json={"slot": "s"}).json()["session_id"]
    assert asyncio.run(server.hub.game(sid2))["meta"]["origin"] == "loaded"


async def test_npc_lines_are_handed_over_word_for_word(monkeypatch):
    g = state.new_game("Wren", seed=1)
    ctx = FakeToolContext(g)

    async def fake_dialogue(tool_context, brief, words, check):
        return {"line": "Two wolves. Bring me the pelts.", "mood": "tired", "disposition_change": 0,
                "remember": "", "suggested_replies": []}
    monkeypatch.setattr(agents, "ask_dialogue", fake_dialogue)
    await tools.move("north", ctx)
    r = tools.talk_to("Maren", ctx)
    assert "Don't speak as them" in r["narrate"]
    r = await tools.say_to_npc("Any work?", ctx)
    assert r["speak_exactly"] == 'The innkeeper: "Two wolves. Bring me the pelts."' and "word for word" in r["how"]
    assert "never add a second line" in agents.GM_INSTRUCTION


def test_combat_results_carry_the_facts():
    g = state.new_game("Wren", seed=1)
    g["meta"]["location_id"] = "ashwood_edge"
    combat.start_combat(g, [{"template": "ash_wolf"}], state.dice(g))
    ctx = FakeToolContext(g)
    r = tools.combat_action("defend", ctx)
    assert r["facts"].startswith("FACTS") and "Ash Wolf" in r["facts"] and "resists: nothing" in r["facts"]


def _generated_fight():
    from genspec import spec
    from dungeon import premise
    g = premise.apply(state.new_game("Wren", seed=2), "x", spec())
    boss = next(k for k, m in g["world"]["monsters"].items() if m["archetype"] == "boss")
    combat.start_combat(g, [{"template": boss}], state.dice(g))
    return g


def test_claims_are_checked_against_the_fight():
    g = _generated_fight()  # the Prelate resists frost and is weak to radiant
    assert combat.check_claims("The frost barely touches it; it resists the cold.", g) == []
    assert combat.check_claims("Holy light sears it, a weakness to radiant power.", g) == []
    assert combat.check_claims("It shrugs off the flames.", g) == ["Nothing in this fight resists fire."]
    assert combat.check_claims("It seems vulnerable to shock.", g) == ["Nothing in this fight is weak to shock."]
    plain = state.new_game("Wren", seed=1)
    combat.start_combat(plain, [{"template": "ash_wolf"}], state.dice(plain))
    assert combat.check_claims("The wolf seems to resist your blows.", plain) == ["Nothing in this fight resists anything."]
    assert combat.check_claims("You are weakened by the bite.", plain) == []


async def _session(g):
    hub = live.Hub(live_models=[])
    sid = await hub.create(g)
    sent = []

    async def send(msg):
        sent.append(msg)
    return live.GameSession(hub, sid, send), sent


async def test_guard_fixes_welcome_back_on_a_new_game_only():
    s, _ = await _session(state.new_game("Wren", seed=1))
    assert await s._guard("Welcome back, Wren. The square is quiet.") == "Welcome, Wren. The square is quiet."
    g = state.new_game("Wren", seed=1)
    g["meta"]["origin"] = "loaded"
    s2, _ = await _session(g)
    assert await s2._guard("Welcome back, Wren.") == "Welcome back, Wren."


async def test_guard_flags_invented_resistances():
    s, sent = await _session(_generated_fight())
    s._turn_text = ["The Prelate laughs as the flames wash over it, immune to fire."]
    await s._check_turn()
    assert {"type": "notice", "level": "info", "text": "Rules check: Nothing in this fight resists fire."} in sent
    sent.clear()
    s._turn_text = ["Your radiant strike finds its weakness to radiant light."]
    await s._check_turn()
    assert sent == []
