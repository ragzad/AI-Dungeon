"""Quest objectives: built with the quest, ticked off by what happens in the game."""
import json

import pytest

from dungeon import agents, premise, quests, state, tools
from genspec import SPEC
from conftest import FakeToolContext


def steps(g, qid):
    return [(o["id"], o["text"]) for o in g["world"]["quests"][qid]["objectives"]]


def test_emberfall_quests_come_with_checklists(g):
    assert steps(g, "wolves") == [("reach", "Find Ashwood Edge"), ("defeat", "Defeat the Ash Wolves"),
                                  ("return", "Return to Maren Holt")]
    assert steps(g, "locket") == [("talk", "Speak to Corwin Vane"), ("find", "Find the Silver Locket"),
                                  ("deliver", "Bring the Silver Locket to Maren Holt")]
    assert g["world"]["quests"]["wolves"]["objectives"][1]["need"] == 2


def test_quests_you_havent_taken_show_nothing(g):
    view = state.public_view(g)
    assert view["quests"] == [] and view["objective"] is None


@pytest.fixture
def offered(monkeypatch):
    async def fake_dialogue(tool_context, brief, words, check):
        return {"line": "Wolves, love. Two of them.", "mood": "hopeful", "disposition_change": 5, "remember": "",
                "offer_quest": "wolves", "suggested_replies": []}
    monkeypatch.setattr(agents, "ask_dialogue", fake_dialogue)


async def test_objectives_tick_off_as_you_play(g, offered):
    ctx = FakeToolContext(g)
    await tools.move("north", ctx)
    tools.talk_to("the innkeeper", ctx)
    await tools.say_to_npc("Any work?", ctx)
    view = state.public_view(state.load(ctx.state))
    cur = view["objective"]
    assert cur["quest"] == "The Ashwood Howls" and cur["text"] == "Find Ashwood Edge" and cur["step"] == 1
    # the giver is still a stranger, so the checklist says so
    wolves = next(q for q in view["quests"] if q["id"] == "wolves")
    assert wolves["objectives"][2]["text"] == "Return to the innkeeper"

    tools.end_conversation(ctx)
    await tools.move("south", ctx)
    r = await tools.move("south", ctx)  # Ashwood Edge: the wolves jump out
    assert r["ok"] and r["mode"] == "combat"
    assert "The Ashwood Howls: Find Ashwood Edge" in r["objectives_done"]

    g2 = state.load(ctx.state)
    g2["world"]["quests"]["wolves"]["progress"] = 1
    quests.sync(g2)
    cur = state.public_view(g2)["objective"]
    assert cur["text"] == "Defeat the Ash Wolves" and (cur["have"], cur["need"], cur["count"]) == (1, 2, True)
    g2["world"]["quests"]["wolves"]["progress"] = 2
    g2["world"]["quests"]["wolves"]["status"] = "ready"
    assert quests.sync(g2) == [("The Ashwood Howls", "Defeat the Ash Wolves")]
    assert any("Defeat the Ash Wolves. Done." in e["text"] for e in g2["journal"])
    assert state.public_view(g2)["objective"]["text"] == "Return to the innkeeper"


def test_finding_the_item_ticks_the_find_step(g):
    q = g["world"]["quests"]["locket"]
    q["status"] = "active"
    state.add_item(g["player"]["inventory"], "silver_locket")
    done = quests.sync(g)
    assert ("Maren's Locket", "Find the Silver Locket") in done
    # it stays done even after you hand it over or lose it
    state.remove_item(g["player"]["inventory"], "silver_locket")
    quests.sync(g)
    assert q["objectives"][1]["done"]


def test_finishing_a_quest_ticks_everything(g):
    q = g["world"]["quests"]["wolves"]
    q["status"] = "done"
    quests.sync(g)
    assert all(o["done"] for o in q["objectives"])


def test_old_saves_get_objectives_quietly(g, tmp_path):
    g["world"]["quests"]["wolves"]["status"] = "ready"
    g["world"]["quests"]["wolves"]["progress"] = 2
    for q in g["world"]["quests"].values():
        q.pop("objectives")
    data = json.loads(state.to_save(g))
    (tmp_path / "old.json").write_text(json.dumps(data))
    back = state.load_slot(tmp_path, "old")
    obs = back["world"]["quests"]["wolves"]["objectives"]
    assert [o["done"] for o in obs] == [False, True, False]  # never went there, but the wolves are dead
    assert not any("Done." in e["text"] for e in back["journal"])


def test_premise_boss_quest_has_level_lair_and_fight():
    g = premise.apply(state.new_game("Wren", seed=3), "a drowned abbey", json.loads(json.dumps(SPEC)))
    boss = steps(g, "boss")
    kinds = [o["kind"] for o in g["world"]["quests"]["boss"]["objectives"]]
    assert kinds == ["level", "visit", "defeat", "turn_in"]
    assert boss[0][1] == "Reach level 2" and boss[1][1] == "Find the Prelate's Font"
    assert boss[2][1] == "Defeat the Sunken Prelate"
    hook = g["world"]["quests"]["hook"]
    want = "Defeat the Silt-Walkers" if hook["goal"]["count"] > 1 else "Defeat the Silt-Walker"
    assert steps(g, "hook")[-2][1] == want and steps(g, "hook")[-1][1] == "Return to Brother Mallow"


def test_contact_from_the_opening_becomes_a_step():
    spec = json.loads(json.dumps(SPEC))
    other = {**spec["npcs"][0], "name": "Sister Tallow", "role": "ferrywoman", "where": "start"}
    spec["npcs"].append(other)
    spec["quest"]["contact"] = "Sister Tallow"
    g = premise.apply(state.new_game("Wren", seed=3), "a drowned abbey", spec)
    assert steps(g, "hook")[0] == ("talk", "Speak to Sister Tallow")


def test_plural_names():
    assert quests.plural("Ash Wolf") == "Ash Wolves"
    assert quests.plural("Brine-Crab Swarm") == "Brine-Crab Swarms"
    assert quests.plural("Harpy") == "Harpies"
    assert quests.plural("Watchman") == "Watchmen"
