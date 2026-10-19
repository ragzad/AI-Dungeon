"""The ADK function tools, with the specialist agents faked out."""
import pytest

from dungeon import agents, state, tools


@pytest.fixture
def fake_agents(monkeypatch):
    calls = {"dialogue": [], "creator": []}

    async def fake_dialogue(tool_context, brief, words, check):
        calls["dialogue"].append((brief, words, check))
        return {"line": "Wolves, love. Two of them.", "mood": "hopeful", "disposition_change": 5,
                "remember": "Offered to help.", "share_secret": None, "offer_quest": "wolves",
                "turn_hostile": False, "suggested_replies": ["I'll do it.", "What's it pay?", "Not my problem."]}

    async def fake_creator(tool_context, origin, direction, hint):
        calls["creator"].append((origin, direction, hint))
        return {"name": "Chapel Lane", "description": "A sunken lane.", "features": [], "exits": [],
                "items": ["antidote"], "encounter": [], "encounter_text": "", "npc": None}

    monkeypatch.setattr(agents, "ask_dialogue", fake_dialogue)
    monkeypatch.setattr(agents, "ask_creator", fake_creator)
    return calls


def test_look_around(ctx):
    r = tools.look_around(ctx)
    assert r["ok"] and r["location"] == "Emberfall Square" and r["mode"] == "exploration"


async def test_move_writes_session_state(ctx, fake_agents):
    r = await tools.move("north", ctx)
    assert r["ok"] and ctx.state["meta"]["location_id"] == "tavern"
    assert fake_agents["creator"] == []


async def test_move_into_unexplored_calls_creator(ctx, fake_agents):
    r = await tools.move("west", ctx)
    assert r["ok"] and r["location"] == "Chapel Lane"
    assert fake_agents["creator"][0][1] == "west"
    assert ctx.state["world"]["locations"]["square"]["exits"]["west"].startswith("loc_chapel_lane")


async def test_refusal_leaves_state_alone(ctx, fake_agents):
    before = state.load(ctx.state)
    r = await tools.move("up", ctx)
    assert r["ok"] is False and "can't go" in r["refused"]
    assert state.delta(ctx.state, before) == {}


async def test_conversation_flow(ctx, fake_agents):
    await tools.move("north", ctx)
    r = tools.talk_to("Maren", ctx)
    assert r["mode"] == "dialogue" and r["npc"]["name"] == "The innkeeper"
    r = await tools.say_to_npc("Need a hand?", ctx)
    assert r["npc_says"].startswith("Wolves")
    assert r["effects"]["quest_started"] == "The Ashwood Howls"
    assert ctx.state["world"]["npcs"]["maren"]["memory"] == ["Offered to help."]
    assert ctx.state["dialogue"]["suggested"][0] == "I'll do it."
    brief = fake_agents["dialogue"][0][0]
    assert brief["name"] == "Maren Holt" and "secrets_you_could_share" in brief
    r = tools.end_conversation(ctx)
    assert r["mode"] == "exploration"


async def test_say_without_conversation(ctx, fake_agents):
    r = await tools.say_to_npc("hello?", ctx)
    assert r["ok"] is False and fake_agents["dialogue"] == []


async def test_dialogue_agent_failure_is_friendly(ctx, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(agents, "ask_dialogue", boom)
    await tools.move("north", ctx)
    tools.talk_to("Maren", ctx)
    r = await tools.say_to_npc("hi", ctx)
    assert r["ok"] is False and "distracted" in r["refused"]


async def test_combat_through_tools(ctx, fake_agents):
    await tools.move("south", ctx)
    assert ctx.state["mode"] == "combat"
    count = ctx.state["meta"]["rng"]["count"]
    for _ in range(30):
        if ctx.state["mode"] != "combat":
            break
        r = tools.combat_action("attack", ctx)
        assert r["ok"] and "status" in r
    assert ctx.state["mode"] in ("exploration", "dead")
    assert ctx.state["meta"]["rng"]["count"] > count  # dice state is saved each turn


def test_attack_starts_fight_with_npc(ctx):
    ctx.state["meta"]["location_id"] = "tavern"
    r = tools.attack("Corwin", ctx)
    assert r["ok"] and r["mode"] == "combat"
    assert ctx.state["world"]["npcs"]["corwin"]["hostile"]


def test_take_and_use(ctx):
    assert tools.take_item("lantern", ctx)["ok"]
    assert tools.use_item("potion", ctx)["ok"] is False  # full HP
    r = tools.skill_check("dex", "easy", "vault the well", ctx)
    assert r["ok"] and "success" in r
