"""The player only sees names they've learned."""
import json

import pytest

from dungeon import agents, combat, live, people, premise, state, tools
from genspec import SPEC
from conftest import FakeToolContext


def test_strangers_start_unnamed_unless_the_sign_says(g):
    npcs = g["world"]["npcs"]
    assert not people.known(npcs["maren"]) and not people.known(npcs["corwin"])
    assert people.known(npcs["brannoc"])  # it's Brannoc's Forge
    assert people.label(npcs["maren"]) == "the innkeeper"


def test_public_view_never_carries_an_unlearned_name(g):
    g["meta"]["location_id"] = "tavern"
    g["world"]["quests"]["locket"]["status"] = "active"
    state.journal(g, "Maren Holt asked about the locket. Corwin Vane smirked.")
    text = json.dumps(state.public_view(g))
    assert "Maren" not in text and "Corwin" not in text and "Holt" not in text
    view = state.public_view(g)
    assert [n["name"] for n in view["location"]["npcs"]] == ["the innkeeper", "the card player in the corner"]
    assert view["journal"][-1]["text"] == "The innkeeper asked about the locket. The card player in the corner smirked."
    # the quest's own title is masked too, possessive and all
    assert next(q for q in view["quests"] if q["id"] == "locket")["title"] == "The innkeeper's Locket"


def test_mask_keeps_sentences_reading_right(g):
    assert people.mask(g, "Maren's eyes narrow. Ask Maren.") == "The innkeeper's eyes narrow. Ask the innkeeper."
    people.reveal(g, "maren")
    assert people.mask(g, "Ask Maren.") == "Ask Maren."


def test_tool_results_use_the_description(ctx):
    ctx.state["meta"] = {**ctx.state["meta"], "location_id": "tavern"}
    r = tools.look_around(ctx)
    text = json.dumps(r)
    assert "Maren" not in text and "the innkeeper (name not known yet)" in r["people"]
    assert "the innkeeper" in r["strangers"]
    r = tools.talk_to("the innkeeper", ctx)  # you can only ask for who you can see
    assert r["ok"] and r["talking_to"] == "the innkeeper" and "Maren" not in json.dumps(r)


def _say(monkeypatch, line, **extra):
    async def fake(tool_context, brief, words, check):
        fake.brief = brief
        return {"line": line, "mood": "", "disposition_change": 0, "remember": "", "suggested_replies": [], **extra}
    monkeypatch.setattr(agents, "ask_dialogue", fake)
    return fake


async def test_an_introduction_reveals_the_name(ctx, monkeypatch):
    ctx.state["meta"] = {**ctx.state["meta"], "location_id": "tavern"}
    tools.talk_to("innkeeper", ctx)
    fake = _say(monkeypatch, "What'll it be, love?")
    r = await tools.say_to_npc("Hello", ctx)
    assert fake.brief["player_knows_your_name"] is False and fake.brief["player_calls_you"] == "the innkeeper"
    assert "names_learned" not in r and not people.known(ctx.state["world"]["npcs"]["maren"])
    _say(monkeypatch, "I'm Maren Holt, and this is my inn.")
    r = await tools.say_to_npc("Who are you?", ctx)
    assert r["names_learned"].startswith("The player now knows: Maren Holt")
    assert r["speak_exactly"].startswith('Maren Holt: "I\'m Maren Holt')
    g = state.load(ctx.state)
    view = state.public_view(g)
    assert view["learned"] == ["Maren Holt"] and view["dialogue"]["name"] == "Maren Holt"
    assert any(e["text"] == "Learned a name: the innkeeper is Maren Holt." for e in g["journal"])


async def test_introduced_flag_reveals_even_without_the_name_in_the_line(ctx, monkeypatch):
    ctx.state["meta"] = {**ctx.state["meta"], "location_id": "tavern"}
    tools.talk_to("innkeeper", ctx)
    _say(monkeypatch, "Folk round here call me by my late husband's name.", introduced=True)
    await tools.say_to_npc("Who are you?", ctx)
    assert people.known(ctx.state["world"]["npcs"]["maren"])


async def test_being_named_by_someone_else_reveals_them(ctx, monkeypatch):
    ctx.state["meta"] = {**ctx.state["meta"], "location_id": "tavern"}
    tools.talk_to("innkeeper", ctx)
    _say(monkeypatch, "Watch Corwin over there, he's light-fingered.")
    r = await tools.say_to_npc("Who's that?", ctx)
    npcs = ctx.state["world"]["npcs"]
    assert people.known(npcs["corwin"]) and not people.known(npcs["maren"])
    assert "Corwin Vane" in r["names_learned"]


def test_strangers_fight_as_strangers(g):
    g["meta"]["location_id"] = "tavern"
    from dungeon import dialogue
    dialogue.start_fight(g, "corwin", state.dice(g), "He draws a knife.")
    names = [c["name"] for cid, c in g["combat"]["combatants"].items() if cid != "player"]
    assert names == ["the card player in the corner"] and "Corwin" not in combat.facts(g)


def test_saves_keep_what_you_know_and_old_saves_know_everyone(g, tmp_path):
    people.reveal(g, "maren")
    state.save_slot(tmp_path, "s", g)
    back = state.load_slot(tmp_path, "s")
    assert people.known(back["world"]["npcs"]["maren"]) and not people.known(back["world"]["npcs"]["corwin"])
    data = json.loads(state.to_save(g))
    for n in data["game"]["world"]["npcs"].values():
        n.pop("known")
    (tmp_path / "old.json").write_text(json.dumps(data))
    old = state.load_slot(tmp_path, "old")
    assert all(people.known(n) for n in old["world"]["npcs"].values())


def test_premise_npcs_get_descriptors_and_signs_count():
    spec = json.loads(json.dumps(SPEC))
    spec["npcs"].append({**spec["npcs"][0], "name": "Sister Tallow", "role": "ferrywoman of the lower docks",
                         "descriptor": "a woman in a salt-stiff coat", "where": "start"})
    spec["npcs"].append({**spec["npcs"][0], "name": "Harl Gant", "role": "net-mender", "descriptor": "Harl the mender",
                         "where": "start"})
    g = premise.apply(state.new_game("Wren", seed=3), "a drowned abbey", spec)
    by = {n["name"]: n for n in g["world"]["npcs"].values()}
    assert people.known(by["Brother Mallow"])  # Mallow's Cell
    assert people.label(by["Sister Tallow"]) == "a woman in a salt-stiff coat"
    assert people.label(by["Harl Gant"]) == "the net-mender"  # a descriptor with the name in it is thrown out


def test_from_role():
    assert people.from_role("innkeeper of the Gutter Lantern") == "the innkeeper"
    assert people.from_role("A retired harbourmaster, who drinks") == "the retired harbourmaster"


async def test_gm_narration_is_put_right_on_screen(g):
    class Hub:
        async def game(self, sid):
            return g
    s = live.GameSession(Hub(), "x", None)
    s.turns = 3
    assert await s._guard("Maren Holt waves you over.") == "The innkeeper waves you over."
