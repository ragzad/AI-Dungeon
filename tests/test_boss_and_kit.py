"""Premise worlds: a reachable boss, enough monsters, and a starting kit of their own."""
import json

import pytest

from dungeon import combat, config, dialogue, forge, live, premise, state, world
from dungeon.state import GameError

from genspec import spec


def game(s=None, seed=3):
    return premise.apply(state.new_game("Wren", seed=seed), "a drowned cathedral", s or spec())


def test_short_monster_lists_are_counted():
    s = spec()
    assert premise.monster_needs(s) == {"tier1": 0, "tier2": 1, "boss": 0}
    s["monsters"] = s["monsters"][:1]
    need = premise.monster_needs(s)
    assert need["boss"] == 1 and need["tier1"] >= 1 and sum(need.values()) + 1 >= premise.MIN_MONSTERS


def test_repair_tops_up_without_a_model():
    s = spec()
    s["monsters"] = s["monsters"][:1]
    out = premise.repair(s, "x")
    mons = out["monsters"]
    assert premise.MIN_MONSTERS <= len(mons) <= premise.MAX_MONSTERS
    assert sum(m["archetype"] == "boss" for m in mons) == 1
    assert not any(premise.monster_needs(out).values())


def test_merge_keeps_the_boss_and_caps_at_six():
    s = spec()
    extra = [{"name": f"Reef Thing {i}", "archetype": "beast", "tier": 1} for i in range(6)]
    out = premise.merge_fixup(s, {"monsters": extra, "renames": []})
    assert len(out["monsters"]) == 6
    assert any(m["archetype"] == "boss" for m in out["monsters"])


def test_boss_lair_is_built_beyond_an_opening_place():
    w, _, _ = premise.build_world(spec())
    locs = w["locations"]
    nave = locs[locs["start"]["exits"]["north"]]
    approach = locs[nave["exits"]["north"]]
    lair = locs[approach["exits"]["north"]]
    assert approach["name"] == "The Flooded Crypt" and lair["name"] == "The Prelate's Font"
    assert (approach["x"], approach["y"], lair["y"]) == (0, -2, -3)
    assert approach["min_level"] == lair["min_level"] == premise.BOSS_LEVEL
    (boss,) = lair["encounter"]["enemies"]
    m = w["monsters"][boss]
    assert m["archetype"] == "boss" and m["tier"] == 2  # tier 3 asked for, clamped so it's reachable
    assert approach["encounter"]["enemies"]
    # the tier 2 mail lies on the way
    assert [i["id"] for i in approach["items"]] == ["i_tidewrack_mail"]
    q = w["quests"]["boss"]
    assert q["status"] == "locked" and q["goal"]["template"] == boss and q["title"] == "Silence the Prelate"


def test_lair_gate_and_boss_fight():
    g = game()
    d = state.dice(g)
    g["world"]["locations"][g["world"]["locations"]["start"]["exits"]["north"]].pop("encounter")
    world.move(g, "north", d)
    with pytest.raises(GameError, match="level 2"):
        world.move(g, "north", d)
    combat.gain_xp(g, g["player"]["xp_next"])
    assert g["player"]["level"] == 2
    world.move(g, "north", d)
    g["combat"] = None
    g["mode"] = "exploration"
    world.move(g, "north", d)
    foes = [c for c in g["combat"]["combatants"].values() if c["side"] == "enemy"]
    assert len(foes) == 1 and foes[0]["name"] == "The Sunken Prelate"


def test_hook_unlocks_the_boss_quest_and_journal_points_the_way():
    g = game()
    assert any(e["text"].startswith("Rumour: They say the Prelate") for e in g["journal"])
    assert not any(q["id"] == "boss" for q in state.public_view(g)["quests"])
    (nid,) = g["world"]["npcs"]
    g["world"]["quests"]["hook"]["status"] = "ready"
    done = dialogue.turn_in(g, nid)
    assert done[0]["new_quests"] == ["Silence the Prelate"]
    assert g["world"]["quests"]["boss"]["status"] == "active"
    assert any("The Prelate's Font" in e["text"] and "New quest" in e["text"] for e in g["journal"])
    # the hook's XP gets a normal player to level 2, and the journal says they're ready
    assert g["player"]["level"] == 2
    combat.gain_xp(g, 0)
    g2 = game()
    g2["world"]["quests"]["boss"]["status"] = "active"
    combat.gain_xp(g2, g2["player"]["xp_next"])
    assert any("you feel ready now" in e["text"] for e in g2["journal"])


def test_npcs_know_the_rumour():
    g = game()
    (nid,) = g["world"]["npcs"]
    brief = dialogue.brief(g, nid)
    assert "Prelate's Font" in brief["rumours_you_know"][0]


def test_every_premise_world_gets_a_boss_even_without_one():
    s = spec()
    s["monsters"] = [m for m in s["monsters"] if m["archetype"] != "boss"]
    s.pop("boss_lair")
    w, _, _ = premise.build_world(s, seed="b")
    assert any(l.get("boss") for l in w["locations"].values())
    assert w["quests"]["boss"]["goal"]["type"] == "defeat"


def test_starting_kit_is_the_worlds_own():
    g = game()
    p = g["player"]
    weapon = state.item_info(p["equipped"]["weapon"], g)
    assert weapon["name"] == "Barnacle Hook" and weapon["tier"] == 1 and weapon["starter"]
    assert weapon["on_hit"]["status"] == "bleeding"  # a free perk, picked to suit piercing
    assert weapon["damage"] == "1d6" and weapon["hit"] == 1
    drink = next(state.item_info(i["id"], g) for i in p["inventory"] if state.item_info(i["id"], g).get("archetype") == "potion")
    assert drink["name"] == "Brine Cordial" and drink["tier"] == 1  # a bomb was asked for; it still heals
    assert any(b["kind"] == "heal" for b in drink["use"]["blocks"])
    assert not any(i["id"] in ("rusty_sword", "healing_potion") for i in p["inventory"])
    assert p["equipped"]["weapon"] not in g["world"]["loot"]["1"]


def test_starter_weapons_hold_up_against_the_rusty_sword():
    for arch in ("light_weapon", "heavy_weapon", "ranged", "focus"):
        _, w, _ = forge.make_item({"name": "X", "archetype": arch, "damage_type": "fire"}, 1, starter=True)
        avg = sum(map(int, w["damage"].split("d")[1:])) / 2 + 0.5 + w["hit"] * 0.5
        assert avg >= 4 and w.get("on_hit")
        _, plain, _ = forge.make_item({"name": "X", "archetype": arch, "damage_type": "fire", "on_hit_status": "burning"}, 1)
        assert plain["damage"] <= w["damage"] or plain["damage"] == "1d10"


def test_missing_draught_still_gives_a_healing_potion():
    s = spec()
    s.pop("starting_consumable")
    s["items"] = [i for i in s["items"] if i["archetype"] != "potion"]
    g = game(s)
    names = [state.item_info(i["id"], g)["name"] for i in g["player"]["inventory"]]
    assert "Saltmarrow Draught" in names


class FakeHub(live.Hub):
    def __init__(self, replies):
        super().__init__(live_models=[])
        self.replies = replies
        self.asked = []

    async def _ask(self, runner, app, payload):
        self.asked.append((app, payload))
        reply = self.replies[app]
        if isinstance(reply, Exception):
            raise reply
        return json.loads(json.dumps(reply))


async def test_opening_tops_up_monsters_and_renames_in_one_call(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    short = spec()
    short["monsters"] = short["monsters"][:2]
    short["npcs"][0]["name"] = "Silas"
    short["quest"]["giver"] = "Silas"
    fix = {"monsters": [{"name": "Choir Eel", "archetype": "skirmisher", "tier": 2, "damage_type": "shock"},
                        {"name": "The Bell-Drowned Abbot", "archetype": "boss", "tier": 2, "damage_type": "necrotic"}],
           "renames": [{"old": "Silas", "new": "Cantor Ebb"}]}
    hub = FakeHub({"opening": short, "fixup": fix})
    out = await hub.opening("a drowned cathedral")
    assert [a for a, _ in hub.asked] == ["opening", "fixup"]
    req = hub.asked[1][1]
    assert req["monsters_needed"]["boss"] == 1 and req["rename"] == {"Silas": "a stock fantasy name"}
    assert len(out["monsters"]) == 4 and out["npcs"][0]["name"] == "Cantor Ebb" and out["quest"]["giver"] == "Cantor Ebb"
    assert "ebb" in json.loads((tmp_path / "names_seen.json").read_text())
    # cached, so the same premise costs nothing next time
    hub.asked.clear()
    assert await hub.opening("a drowned cathedral") == out and hub.asked == []


async def test_opening_survives_a_failed_top_up(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    short = spec()
    short["monsters"] = short["monsters"][:1]
    hub = FakeHub({"opening": short, "fixup": RuntimeError("429 RESOURCE_EXHAUSTED")})
    out = await hub.opening("a drowned cathedral")
    g = premise.apply(state.new_game("Wren", seed=1), "a drowned cathedral", out)
    mons = [m for m in g["world"]["monsters"].values() if not m.get("npc") and m.get("xp", 0) > 5]
    assert len(mons) >= premise.MIN_MONSTERS and any(m["archetype"] == "boss" for m in mons)


def test_boss_quest_never_shares_the_hooks_title():
    s = spec()
    s["boss_lair"]["quest_title"] = s["quest"]["title"]
    w, _, _ = premise.build_world(s)
    assert w["quests"]["boss"]["title"] == "Face The Sunken Prelate"


def test_a_fight_never_drops_the_same_gear_twice():
    g = game()
    dirk = next(k for k, v in g["world"]["items"].items() if v.get("slot") == "armour")
    m = next(k for k, v in g["world"]["monsters"].items() if v["archetype"] == "brute")
    g["world"]["monsters"][m]["loot"] = [dirk]
    g["world"]["loot"] = {"1": [dirk], "2": [dirk], "3": [dirk]}
    d = state.dice(g)
    combat.start_combat(g, [{"template": m}] * 3, d)
    for c in g["combat"]["combatants"].values():
        if c["side"] == "enemy":
            c["hp"] = 0
    combat._finish(g, "victory", [], d)
    assert g["combat"]["rewards"]["items"].count(dirk) <= 1
    assert sum(i["qty"] for i in g["player"]["inventory"] if i["id"] == dirk) <= 1
