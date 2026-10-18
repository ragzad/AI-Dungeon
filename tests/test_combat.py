import pytest

from dungeon import combat, state
from dungeon.dice import ScriptedDice
from dungeon.state import GameError

from conftest import put_in


def fight(g, rolls, enemies=("ash_wolf",)):
    """Start a fight where the player wins initiative unless rolls say otherwise."""
    return combat.start_combat(g, [{"template": t} for t in enemies], ScriptedDice(rolls))


def test_initiative_orders_by_roll_plus_dex(g):
    # player 10+2=12, wolf A 15+2=17, wolf B 3+2=5; wolf A then acts: ability check 99 (no), attack 1 (miss)
    fight(g, [10, 15, 3, 99, 1], enemies=("ash_wolf", "ash_wolf"))
    cb = g["combat"]
    assert cb["order"] == ["e1", "player", "e2"]
    assert cb["order"][cb["turn"]] == "player"
    assert g["mode"] == "combat"
    assert cb["combatants"]["e1"]["name"] == "Ash Wolf A"


def test_hit_and_damage(g):
    fight(g, [20, 1])
    # attack 15+5=20 vs AC 12, damage 4+3=7; wolf turn: ability no (99), attack misses (1)
    combat.player_action(g, "attack", ScriptedDice([15, 4, 99, 1]))
    assert g["combat"]["combatants"]["e1"]["hp"] == 9 - 7
    assert g["player"]["hp"] == 30


def test_miss_on_low_roll(g):
    fight(g, [20, 1])
    r = combat.player_action(g, "attack", ScriptedDice([5, 99, 1]))
    assert r["events"][0]["kind"] == "miss"
    assert g["combat"]["combatants"]["e1"]["hp"] == 9


def test_natural_one_always_misses_and_twenty_crits(g):
    fight(g, [20, 1])
    g["combat"]["combatants"]["e1"]["ac"] = 2
    r = combat.player_action(g, "attack", ScriptedDice([1, 99, 1]))
    assert r["events"][0]["kind"] == "miss"
    g["combat"]["combatants"]["e1"]["ac"] = 30
    g["combat"]["combatants"]["e1"]["hp"] = 50
    r = combat.player_action(g, "attack", ScriptedDice([20, 4, 4, 99, 1]))
    assert r["events"][0]["kind"] == "crit"
    assert g["combat"]["combatants"]["e1"]["hp"] == 50 - (4 + 4 + 3)


def test_defend_raises_ac_until_next_turn(g):
    fight(g, [20, 1])
    # wolf rolls 11+3=14: misses while the player defends (AC 16)...
    r = combat.player_action(g, "defend", ScriptedDice([99, 11]))
    assert r["events"][0]["kind"] == "defend"
    assert r["events"][-1]["kind"] == "miss" and r["events"][-1]["ac"] == 16
    # ...and the guard drops at the start of the player's next turn, so the same roll hits AC 14
    assert not any(s["name"] == "defending" for s in g["player"]["status"])
    r = combat.player_action(g, "attack", ScriptedDice([2, 99, 11, 3]))
    assert r["events"][-1]["kind"] == "hit"
    assert g["player"]["hp"] == 30 - 4


def test_enemy_ability_applies_status_and_it_ticks(g):
    fight(g, [20, 1])
    # player misses; wolf: ability roll 10 (<=35) so Savage Bite, hits on 15 for 3+1, bleeding.
    # bleeding then ticks for 2 at the start of the player's turn
    combat.player_action(g, "attack", ScriptedDice([2, 10, 15, 3, 2]))
    assert g["player"]["hp"] == 30 - 4 - 2
    assert g["player"]["status"] == [{"name": "bleeding", "turns": 1}]
    assert g["combat"]["combatants"]["e1"]["ability"]["uses"] == 0
    combat.player_action(g, "attack", ScriptedDice([2, 1, 2]))
    assert g["player"]["hp"] == 30 - 4 - 2 - 2
    assert g["player"]["status"] == []


def test_poison_wears_off(g):
    fight(g, [20, 1])
    pc = g["combat"]["combatants"]["e1"]
    pc["hp"] = 100
    pc["max_hp"] = 100
    pc["status"] = [{"name": "poisoned", "turns": 2}]
    combat.player_action(g, "attack", ScriptedDice([2, 1, 99, 1]))  # wolf takes 1 poison, then misses
    assert pc["hp"] == 99 and pc["status"][0]["turns"] == 1
    combat.player_action(g, "attack", ScriptedDice([2, 1, 99, 1]))
    assert pc["hp"] == 98 and pc["status"] == []


def test_stunned_enemy_loses_turn(g):
    fight(g, [20, 1])
    g["combat"]["combatants"]["e1"]["status"] = [{"name": "stunned", "turns": 1}]
    # only the player's attack roll is used; the wolf skips
    r = combat.player_action(g, "attack", ScriptedDice([2]))
    assert any("stunned" in e["text"] for e in r["events"])
    assert g["combat"]["combatants"]["e1"]["status"] == []


def test_victory_gives_xp_loot_and_quest_progress(g):
    put_in(g, "ashwood_edge")
    g["world"]["quests"]["wolves"]["status"] = "active"
    g["world"]["quests"]["wolves"]["goal"]["count"] = 1
    fight(g, [20, 1])
    g["combat"]["combatants"]["e1"]["hp"] = 1
    r = combat.player_action(g, "attack", ScriptedDice([15, 3]))
    assert r["outcome"] == "victory"
    assert g["mode"] == "exploration"
    assert g["player"]["xp"] == 25
    assert state.inventory_count(g, "wolf_pelt") == 1
    assert g["world"]["quests"]["wolves"]["status"] == "ready"
    assert "encounter" not in state.location(g)


def test_level_up(g):
    g["player"]["xp"] = 90
    fight(g, [20, 1])
    g["combat"]["combatants"]["e1"]["hp"] = 1
    combat.player_action(g, "attack", ScriptedDice([15, 3]))
    p = g["player"]
    assert p["level"] == 2 and p["max_hp"] == 38 and p["xp_next"] == 400


def test_defeat_sets_dead(g):
    g["player"]["hp"] = 2
    fight(g, [20, 1])
    r = combat.player_action(g, "attack", ScriptedDice([2, 99, 15, 5]))
    assert r["outcome"] == "defeat"
    assert g["mode"] == "dead"
    with pytest.raises(GameError):
        combat.player_action(g, "attack", ScriptedDice([10]))


def test_flee_success_goes_back(g):
    put_in(g, "ashwood_edge")
    fight(g, [20, 1])
    r = combat.player_action(g, "flee", ScriptedDice([18]))
    assert r["outcome"] == "fled"
    assert g["mode"] == "exploration"
    assert g["meta"]["location_id"] == "square"


def test_flee_failure_wastes_turn(g):
    fight(g, [20, 1])
    r = combat.player_action(g, "flee", ScriptedDice([2, 99, 1]))
    assert r["outcome"] is None and g["mode"] == "combat"
    assert r["events"][0]["kind"] == "flee_fail"


def test_power_strike_uses_charges(g):
    fight(g, [20, 1])
    g["combat"]["combatants"]["e1"]["hp"] = 40
    combat.player_action(g, "power_strike", ScriptedDice([15, 5, 6, 99, 1]))
    assert g["combat"]["combatants"]["e1"]["hp"] == 40 - (5 + 3 + 6)
    assert g["player"]["abilities"]["power_strike"] == 1
    combat.player_action(g, "power_strike", ScriptedDice([1, 99, 1]))
    with pytest.raises(GameError):
        combat.player_action(g, "power_strike", ScriptedDice([15]))


def test_firebomb_burns(g):
    state.add_item(g["player"]["inventory"], "firebomb")
    fight(g, [20, 1])
    g["combat"]["combatants"]["e1"]["hp"] = 30
    combat.player_action(g, "item", ScriptedDice([3, 3, 1, 99, 1]), item="firebomb")
    e = g["combat"]["combatants"]["e1"]
    assert e["hp"] == 30 - 6 - 1  # bomb, then burning ticks at its turn start
    assert state.inventory_count(g, "firebomb") == 0


def test_potion_heals_in_combat(g):
    g["player"]["hp"] = 10
    fight(g, [20, 1])
    combat.player_action(g, "item", ScriptedDice([4, 4, 99, 1]), item="potion")
    assert g["player"]["hp"] == 20
    assert state.inventory_count(g, "healing_potion") == 1


def test_cunning_enemy_opens_with_ability(g):
    combat.start_combat(g, [{"template": "bandit"}], ScriptedDice([20, 1]))
    # bandit always uses Poisoned Blade first: hit 15, damage 2+2
    combat.player_action(g, "attack", ScriptedDice([2, 15, 2, 1]))
    assert g["player"]["hp"] == 30 - 4 - 1
    assert g["player"]["status"][0]["name"] == "poisoned"


def test_cant_act_out_of_turn_or_outside_fight(g):
    with pytest.raises(GameError):
        combat.player_action(g, "attack", ScriptedDice([10]))
    fight(g, [20, 1])
    with pytest.raises(GameError):
        combat.player_action(g, "dance", ScriptedDice([10]))
