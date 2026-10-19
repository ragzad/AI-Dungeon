import pytest

from dungeon import state, world
from dungeon.dice import Dice, ScriptedDice
from dungeon.state import GameError

from conftest import put_in


def test_describe_lists_exits_people_items(g):
    put_in(g, "tavern")
    d = world.describe(g)
    assert d["location"] == "The Gutter Lantern"
    assert any("the innkeeper (name not known yet" in p for p in d["people"])
    assert d["exits"] == ["south: Emberfall Square"]


def test_move_by_direction_and_by_name(g):
    r = world.move(g, "north", Dice(1))
    assert r["location"] == "The Gutter Lantern" and r["first_visit"]
    world.move(g, "back", Dice(1))
    assert g["meta"]["location_id"] == "square"
    world.move(g, "the forge", Dice(1))
    assert g["meta"]["location_id"] == "smithy"
    assert any("Brannoc" in e["text"] for e in g["journal"])


def test_bad_exit_refused(g):
    with pytest.raises(GameError):
        world.move(g, "up", Dice(1))


def test_unexplored_exit_asks_for_creator(g):
    r = world.move(g, "west", Dice(1))
    assert r == {"needs_creation": {"direction": "west", "hint": "a sunken lane towards the old chapel"}}
    assert g["meta"]["location_id"] == "square"


def test_encounter_starts_combat(g):
    r = world.move(g, "south", Dice(3))
    assert g["mode"] == "combat"
    assert "encounter" in r and len(g["combat"]["combatants"]) == 3


def test_cant_walk_out_of_combat(g):
    world.move(g, "south", Dice(3))
    with pytest.raises(GameError):
        world.move(g, "north", Dice(3))


def test_walking_off_ends_dialogue(g):
    put_in(g, "tavern")
    g["mode"] = "dialogue"
    g["dialogue"] = {"npc_id": "maren", "suggested": [], "last_line": None, "turns": 0, "mood": "warm"}
    r = world.move(g, "south", Dice(1))
    assert r["left_conversation_with"] == "Maren Holt"
    assert g["mode"] == "exploration" and g["dialogue"] is None


def test_add_location_validates_creator_output(g):
    spec = {
        "name": "Chapel Lane", "description": "A sunken lane between leaning walls.",
        "features": [{"name": "Gargoyle", "description": "Missing its head."}],
        "exits": [{"direction": "north", "hint": "a broken lychgate"}, {"direction": "sideways", "hint": "nope"}],
        "items": ["healing_potion", "laser_gun"],
        "encounter": ["cinder_ghoul", "dragon"], "encounter_text": "Ash stirs.",
        "npc": {"name": "Old Tam", "role": "gravedigger", "personality": "dour", "voice": "slow",
                "goals": ["dig"], "secret": "There are tunnels.", "disposition": 99, "fights_as": "dragon"},
    }
    new_id = world.add_location(g, "west", spec)
    loc = g["world"]["locations"][new_id]
    assert loc["exits"]["east"] == "square"
    assert "north" in loc["exits"] and "sideways" not in loc["exits"]
    assert loc["items"] == [{"id": "healing_potion", "qty": 1}]
    assert loc["encounter"]["enemies"] == ["cinder_ghoul"]
    assert (loc["x"], loc["y"]) == (-1, 0)
    tam = g["world"]["npcs"]["npc_old_tam"]
    assert tam["disposition"] == 70 and tam["combat"]["template"] == "bandit"
    assert g["world"]["locations"]["square"]["exits"]["west"] == new_id
    with pytest.raises(GameError):
        world.add_location(g, "west", spec)


def test_add_location_needs_name(g):
    with pytest.raises(GameError):
        world.add_location(g, "west", {"name": "", "description": ""})


def test_take_and_drop(g):
    r = world.take(g, "lantern")
    assert r["took"] == "Lantern"
    assert state.inventory_count(g, "lantern") == 1 and state.location(g)["items"] == []
    world.drop(g, "lantern")
    assert state.inventory_count(g, "lantern") == 0
    with pytest.raises(GameError):
        world.take(g, "anvil")


def test_inspect(g):
    assert "NOT AGAIN" in world.inspect(g, "the well")["detail"]
    assert world.inspect(g, "map")["item"] == "Old Map"
    with pytest.raises(GameError):
        world.inspect(g, "dragon")


def test_use_potion_and_equip(g):
    with pytest.raises(GameError):
        world.use_item(g, "potion", Dice(1))  # full health
    g["player"]["hp"] = 10
    r = world.use_item(g, "potion", ScriptedDice([3, 3]))
    assert r["healed"] == 8 and g["player"]["hp"] == 18
    state.add_item(g["player"]["inventory"], "iron_shield")
    before = state.player_ac(g)
    world.use_item(g, "shield", Dice(1))
    assert state.player_ac(g) == before + 1


def test_rest_costs_gold_and_heals(g):
    with pytest.raises(GameError):
        world.rest(g)
    put_in(g, "tavern")
    g["player"]["hp"] = 3
    g["player"]["abilities"]["power_strike"] = 0
    world.rest(g)
    assert g["player"]["hp"] == 30 and g["player"]["gold"] == 7
    assert g["player"]["abilities"]["power_strike"] == 2


def test_skill_check(g):
    r = world.skill_check(g, "dex", "hard", ScriptedDice([14]), "climb the wall")
    assert r["total"] == 16 and r["dc"] == 16 and r["success"]
    assert world.skill_check(g, "str", "impossible", ScriptedDice([]), "lift the inn")["success"] is False
    with pytest.raises(GameError):
        world.skill_check(g, "luck", "easy", ScriptedDice([10]))
