"""Generated content: archetypes, budgets, effect blocks and the fights they make."""
import copy
import json

import pytest

from dungeon import combat, content, forge, premise, state, world
from dungeon.dice import ScriptedDice

GALE = {"name": "Gale Harpy", "description": "All claws and shrieking.", "archetype": "skirmisher", "tier": 1,
        "damage_type": "slashing", "resist": "shock", "weak": "fire",
        "abilities": [{"name": "Gale Shriek", "description": "A scream that tears the air.", "target": "enemy",
                       "blocks": [{"kind": "damage", "damage_type": "psychic"}, {"kind": "status", "status": "blinded"}]}],
        "loot": ["Storm Glass Pistol"]}


def test_items_get_numbers_from_the_budget_not_the_model():
    _, sword, _ = forge.make_item({"name": "Godslayer", "archetype": "heavy_weapon", "tier": 99, "damage": "40d40"}, 1)
    assert sword["tier"] == 1 and sword["damage"] == "1d10" and "40d40" not in json.dumps(sword)
    _, pistol, _ = forge.make_item({"name": "Storm Pistol", "archetype": "ranged", "tier": 2,
                                    "damage_type": "shock", "on_hit_status": "slowed"}, 3)
    # elemental and a rider each cost a die size
    assert pistol["damage"] == "1d4" and pistol["on_hit"] == {"status": "slowed", "chance": 30}
    _, plate, _ = forge.make_item({"name": "Plate", "archetype": "heavy_armour", "tier": 3, "resist": "slashing"}, 3)
    assert plate["ac"] == 4 and "resist" not in plate  # never resistance to plain steel
    assert forge.make_item({"name": "Thing", "archetype": "laser_cannon"}, 1) == (None, None, None)


def test_monsters_follow_archetype_and_fair_play_rules():
    _, m = forge.make_monster(GALE, 1)
    assert (m["hp"], m["ac"], m["attack"], m["damage"]) == (10, 13, 3, "1d6+1")
    assert m["resist"] == ["shock"] and m["weak"] == ["fire"]
    shriek = m["abilities"][0]
    assert shriek["name"] == "Gale Shriek" and [b["kind"] for b in shriek["blocks"]] == ["damage", "status"]
    # a resistance without a weakness is dropped, physical resistance too
    _, m = forge.make_monster({**GALE, "weak": None}, 1)
    assert "resist" not in m
    _, m = forge.make_monster({**GALE, "resist": "slashing"}, 1)
    assert "resist" not in m
    _, boss = forge.make_monster({"name": "Engine Wraith", "archetype": "boss", "tier": 1, "abilities": []}, 3)
    assert boss["tier"] == 2 and boss["abilities"][0]["uses"] == 2


def test_ability_blocks_are_validated_and_repaired():
    a = forge.make_ability({"name": "Nonsense", "target": "self", "blocks": [
        {"kind": "damage"}, {"kind": "status", "status": "stunned"}, {"kind": "laser"}]}, 1, owner="player")
    assert [b["kind"] for b in a["blocks"]] == ["heal"]  # nothing valid for a self ability, so it heals
    a = forge.make_ability({"name": "Storm", "target": "all_enemies", "blocks": [
        {"kind": "damage", "damage_type": "shock"}, {"kind": "status", "status": "stunned"}]}, 1, owner="player")
    assert [b["kind"] for b in a["blocks"]] == ["damage"] and a["uses"] == 1  # no mass stuns
    a = forge.make_ability({"name": "Chain", "target": "enemy", "blocks": [{"kind": "chain"}]}, 1, owner="player")
    assert [b["kind"] for b in a["blocks"]] == ["damage", "chain"]
    summon = forge.make_ability({"name": "Call", "blocks": [{"kind": "summon"}]}, 1, owner="player")
    assert summon["target"] == "self" and summon["blocks"] == [{"kind": "heal", "dice": "2d4+2"}]
    one = forge.make_ability({"name": "A", "blocks": [{"kind": "damage"}]}, 2, owner="player")
    three = forge.make_ability({"name": "B", "blocks": [{"kind": "damage"}, {"kind": "status", "status": "slowed"},
                                                      {"kind": "push"}]}, 2, owner="player")
    assert forge.POWER.index(one["blocks"][0]["dice"]) > forge.POWER.index(three["blocks"][0]["dice"])


def test_encounters_fit_the_budget_and_bosses_fight_alone():
    w = {}
    _, names = forge.register(w, monsters=[GALE, {"name": "Rat Tide", "archetype": "swarm", "tier": 1},
                                           {"name": "Wraith", "archetype": "boss", "tier": 2}])
    mons = w["monsters"]
    gale, rats, boss = names["gale harpy"], names["rat tide"], names["wraith"]
    assert forge.fit_encounter([(gale, mons[gale])] * 3, 2.0, 1) == [gale, gale]
    assert forge.fit_encounter([(rats, mons[rats])] * 3, 2.0, 1) == [rats] * 3
    assert forge.fit_encounter([(boss, mons[boss]), (gale, mons[gale])], 1.5, 2) == [boss]
    assert forge.fit_encounter([(boss, mons[boss])], 2.0, 1) == []
    assert w["monsters"][boss].get("minion") is None or w["monsters"][boss]["minion"] in mons


def _fight(g, template, seed=1):
    g["meta"]["rng"] = {"seed": seed, "count": 0}
    d = state.dice(g)
    combat.start_combat(g, [{"template": template}], d)
    return d


@pytest.fixture
def gen(g):
    w = g["world"]
    forge.register(w, items=[{"name": "Storm Glass Pistol", "archetype": "ranged", "tier": 1, "damage_type": "shock"},
                             {"name": "Salt Ward", "archetype": "scroll", "tier": 1,
                              "use": {"name": "Salt Ward", "target": "self", "blocks": [{"kind": "shield"}]}},
                             {"name": "Flash Jar", "archetype": "bomb", "tier": 1, "damage_type": "fire",
                              "use": {"target": "enemy", "blocks": [{"kind": "status", "status": "blinded"}]}},
                             {"name": "Tide Charm", "archetype": "trinket", "tier": 1, "bonus": "max_hp"}],
                   monsters=[GALE])
    return g


def test_generated_monster_uses_its_signature_and_resists(gen):
    g = gen
    mid = forge.resolve_monster(g["world"], "Gale Harpy", {})
    d = _fight(g, mid)
    cb = g["combat"]
    harpy = next(c for c in cb["combatants"].values() if c["side"] == "enemy")
    assert harpy["resist"] == ["shock"] and harpy["abilities"][0]["name"] == "Gale Shriek"
    # force the harpy's turn with an ability roll that always passes
    combat._use_ability(g, cb, "e1", harpy["abilities"][0], "player", ScriptedDice([15, 4, 3]), [])
    assert any("Gale Shriek" in e["text"] for e in cb["log"])
    assert combat._status(cb["combatants"]["player"], "blinded")
    # fire hits its weak spot for half as much again, shock is halved
    hp = harpy["hp"]
    dealt, notes = combat._hurt(g, cb, "e1", 4, "fire")
    assert dealt == 6 and notes == ["weak spot"] and harpy["hp"] == hp - 6
    dealt, notes = combat._hurt(g, cb, "e1", 4, "shock")
    assert dealt == 2 and notes == ["resisted"]


def test_blinded_and_shielded_change_the_maths(gen):
    g = gen
    d = _fight(g, forge.resolve_monster(g["world"], "Gale Harpy", {}))
    cb = g["combat"]
    pc = cb["combatants"]["player"]
    combat._give_status(g, cb, "player", "shielded", amount=5)
    before = g["player"]["hp"]
    dealt, notes = combat._hurt(g, cb, "player", 7, "slashing")
    assert dealt == 2 and g["player"]["hp"] == before - 2 and not combat._status(pc, "shielded")
    combat._give_status(g, cb, "player", "blinded")
    assert combat._hit_mod(pc) == -3
    combat._give_status(g, cb, "player", "slowed")
    with pytest.raises(state.GameError):
        combat.player_action(g, "flee", d)


def test_player_learns_from_a_scroll_and_uses_it_in_combat(gen):
    g = gen
    scroll = forge.resolve_item(g["world"], "Salt Ward", {})
    state.add_item(g["player"]["inventory"], scroll)
    r = world.use_item(g, "Salt Ward", state.dice(g))
    assert r["learned"] == "Salt Ward" and state.inventory_count(g, scroll) == 0
    aid = g["world"]["items"][scroll]["teaches"]
    assert g["player"]["abilities"][aid] == 2
    view = state.public_view(g)
    assert any(a["name"] == "Salt Ward" and a["generated"] for a in view["player"]["abilities"])
    d = _fight(g, forge.resolve_monster(g["world"], "Gale Harpy", {}))
    if g["combat"]["order"][g["combat"]["turn"]] != "player":
        pytest.skip("harpy won initiative on this seed")
    combat.player_action(g, "Salt Ward", d)
    assert g["player"]["abilities"][aid] == 1
    assert any("Salt Ward" in e["text"] for e in g["combat"]["log"])
    # resting brings generated abilities back too
    g["mode"], g["combat"] = "exploration", None
    g["meta"]["location_id"] = "tavern"
    world.rest(g)
    assert g["player"]["abilities"][aid] == 2 and g["player"]["abilities"]["power_strike"] == 2


def test_gear_slots_bonuses_and_bombs(gen):
    g = gen
    for name in ("Storm Glass Pistol", "Tide Charm", "Flash Jar"):
        state.add_item(g["player"]["inventory"], forge.resolve_item(g["world"], name, {}))
    world.use_item(g, "Storm Glass Pistol", state.dice(g))
    assert state.weapon_type(g) == "shock" and state.attack_bonus(g) == 2 + 3 + 1
    max_hp = g["player"]["max_hp"]
    world.use_item(g, "Tide Charm", state.dice(g))
    assert g["player"]["max_hp"] == max_hp + 5 and g["player"]["equipped"]["trinket"]
    with pytest.raises(state.GameError):
        world.use_item(g, "Flash Jar", state.dice(g))  # bombs are for fights
    d = _fight(g, forge.resolve_monster(g["world"], "Gale Harpy", {}))
    if g["combat"]["order"][g["combat"]["turn"]] != "player":
        pytest.skip("harpy won initiative on this seed")
    combat.player_action(g, "item", d, item="Flash Jar")
    log = " ".join(e["text"] for e in g["combat"]["log"])
    assert "Flash Jar" in log and ("blinded" in log or "falls" in log)


def test_summoner_calls_a_minion_within_limits(g):
    w = g["world"]
    _, names = forge.register(w, monsters=[{"name": "Hive Mother", "archetype": "boss", "tier": 2, "abilities": [
        {"name": "Brood Call", "target": "self", "blocks": [{"kind": "summon"}]}]}])
    boss = names["hive mother"]
    minion = w["monsters"][boss]["minion"]
    assert w["monsters"][minion]["archetype"] == "swarm"
    d = _fight(g, boss)
    cb = g["combat"]
    call = next(a for a in cb["combatants"]["e1"]["abilities"] if a["name"] == "Brood Call")
    for _ in range(5):
        combat._use_ability(g, cb, "e1", call, None, d, [])
    alive = [c for c in cb["combatants"].values() if c["side"] == "enemy" and c["hp"] > 0]
    assert len(alive) == combat.MAX_ENEMIES
    assert all(c["summoned"] for c in alive if c["name"] != "Hive Mother")


def test_loot_tables_and_victory_drops(gen):
    g = gen
    assert g["world"]["loot"]["1"] and set(g["world"]["loot"]["1"]) <= set(g["world"]["items"])
    mid = forge.resolve_monster(g["world"], "Gale Harpy", {})
    assert g["world"]["monsters"][mid]["loot"] == [forge.resolve_item(g["world"], "Storm Glass Pistol", {})]
    pistol = forge.resolve_item(g["world"], "Storm Glass Pistol", {})
    drops = []
    for seed in range(20):
        fresh = copy.deepcopy(g)
        d = _fight(fresh, mid, seed=seed)
        fresh["combat"]["combatants"]["e1"]["hp"] = 0
        combat._finish(fresh, "victory", [], d)
        items = fresh["combat"]["rewards"]["items"]
        assert set(items) <= set(g["world"]["items"])
        drops.append(pistol in items)
    assert 3 <= sum(drops) <= 17  # its own loot drops about half the time


def test_smart_ai_is_deterministic(gen):
    mid = forge.resolve_monster(gen["world"], "Gale Harpy", {})
    logs = []
    for _ in range(2):
        g = copy.deepcopy(gen)
        d = _fight(g, mid, seed=9)
        for _ in range(6):
            if g["combat"]["outcome"]:
                break
            combat.player_action(g, "defend", d)
        logs.append([e["text"] for e in g["combat"]["log"]])
    assert logs[0] == logs[1]


def test_new_places_can_bring_new_monsters(gen):
    g = gen
    g["meta"]["location_id"] = "ashwood_edge"
    spec = {"name": "Glass Dunes", "description": "Sand fused to glass.", "features": [],
            "exits": [], "items": ["Mirror Blade"], "encounter_text": "Shards rise.",
            "new_items": [{"name": "Mirror Blade", "archetype": "light_weapon", "tier": 3}],
            "new_monsters": [{"name": "Shard Golem", "archetype": "tank", "tier": 3, "damage_type": "slashing",
                              "abilities": [{"name": "Glass Skin", "target": "self", "blocks": [{"kind": "shield"}]}]}],
            "encounter": [{"monster": "Shard Golem", "count": 2}]}
    new_id = world.add_location(g, "south", spec)
    loc = g["world"]["locations"][new_id]
    golem = g["world"]["monsters"][forge.resolve_monster(g["world"], "Shard Golem", {})]
    blade = g["world"]["items"][forge.resolve_item(g["world"], "Mirror Blade", {})]
    # a level 1 player two steps out gets a tier 1 place, so the new things are clamped down
    assert loc["tier"] == 1 and golem["tier"] == 1 and blade["tier"] == 1
    assert loc["encounter"]["enemies"] == [forge.resolve_monster(g["world"], "Shard Golem", {})] * 2
    assert loc["items"]


def test_emberfall_and_old_saves_still_work(tmp_path, g):
    # an old save has no items/monsters/abilities registry and no shield or trinket slot
    old = json.loads(json.dumps(g))
    for k in ("items", "monsters", "abilities", "loot"):
        old["world"].pop(k, None)
    old["meta"].pop("setting", None)
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"version": state.VERSION, "game": old}))
    back = state.load_slot(tmp_path, "old")
    view = state.public_view(back)
    assert view["setting"]["name"] == "Emberfall"
    assert [a["id"] for a in view["player"]["abilities"]] == ["power_strike", "second_wind"]
    put = copy.deepcopy(back)
    put["meta"]["location_id"] = "ashwood_edge"
    world.move(put, "north", state.dice(put))


def test_premise_world_has_its_own_kit_and_content():
    from test_premise import OPENING
    spec = json.loads(json.dumps(OPENING))
    spec["items"] = [{"name": "Red Draught", "archetype": "potion", "tier": 1},
                     {"name": "Sky Hook", "archetype": "light_weapon", "tier": 2}]
    spec["monsters"] = [GALE]
    spec["places"][1]["encounter"] = [{"monster": "Gale Harpy", "count": 2}]
    spec["starting_weapon"] = {"name": "Dock Hook", "archetype": "heavy_weapon", "tier": 3}
    spec["npcs"][0]["sells"] = ["Sky Hook", "Red Draught"]
    spec["quest"] = {"title": "Clip Their Wings", "desc": "x", "giver": "Vex Marlowe", "kind": "defeat",
                     "monster": "Gale Harpy", "reward_ability": {"name": "Updraft", "target": "self",
                                                                 "blocks": [{"kind": "status", "status": "hasted"}]}}
    g = premise.apply(state.new_game("Wren", seed=2), "sky heist", spec)
    p = g["player"]
    hook = g["world"]["items"][p["equipped"]["weapon"]]
    assert hook["name"] == "Dock Hook" and hook["tier"] == 1
    assert any(g["world"]["items"].get(i["id"], {}).get("name") == "Red Draught" and i["qty"] == 2 for i in p["inventory"])
    vault = g["world"]["locations"][g["world"]["locations"]["start"]["exits"]["east"]]
    harpy = forge.resolve_monster(g["world"], "Gale Harpy", {})
    assert vault["encounter"]["enemies"] == [harpy, harpy]
    q = g["world"]["quests"]["hook"]
    assert q["goal"] == {"type": "defeat", "template": harpy, "count": 2}
    assert g["world"]["abilities"][q["reward"]["ability"]]["name"] == "Updraft"
