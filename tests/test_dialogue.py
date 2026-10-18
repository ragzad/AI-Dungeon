import pytest

from dungeon import dialogue, state
from dungeon.dice import Dice, ScriptedDice
from dungeon.state import GameError

from conftest import put_in


def reply(**kw):
    base = {"line": "Aye.", "mood": "calm", "disposition_change": 0, "remember": "", "share_secret": None,
            "offer_quest": None, "turn_hostile": False, "suggested_replies": ["a", "b", "c", "d"]}
    base.update(kw)
    return base


@pytest.fixture
def at_tavern(g):
    put_in(g, "tavern")
    return g


def test_start_switches_mode(at_tavern):
    g = at_tavern
    r = dialogue.start(g, "maren", Dice(1))
    assert g["mode"] == "dialogue" and g["dialogue"]["npc_id"] == "maren"
    assert r["first_meeting"] is True
    with pytest.raises(GameError):
        dialogue.start(g, "brannoc", Dice(1))  # he's at the forge


def test_hostile_npc_goes_straight_to_combat(at_tavern):
    g = at_tavern
    g["world"]["npcs"]["corwin"]["hostile"] = True
    r = dialogue.start(g, "corwin", ScriptedDice([20, 1]))
    assert r["hostile"] and g["mode"] == "combat"


def test_reply_updates_disposition_memory_and_suggestions(at_tavern):
    g = at_tavern
    dialogue.start(g, "maren", Dice(1))
    fx = dialogue.apply_reply(g, "maren", "hello", reply(disposition_change=40, remember="Was polite."), None, Dice(1))
    assert fx["disposition"]["after"] == 55 + 15  # clamped to +15
    assert g["world"]["npcs"]["maren"]["memory"] == ["Was polite."]
    assert len(g["dialogue"]["suggested"]) == 3
    assert g["dialogue"]["last_line"] == "Aye."


def test_secret_needs_enough_disposition(at_tavern):
    g = at_tavern
    dialogue.start(g, "corwin", Dice(1))
    fx = dialogue.apply_reply(g, "corwin", "tell me", reply(share_secret="corwin_has_locket"), None, Dice(1))
    assert fx.get("refused_secret") and not any("locket" in e["text"] for e in g["journal"])
    g["world"]["npcs"]["corwin"]["disposition"] = 70
    fx = dialogue.apply_reply(g, "corwin", "tell me", reply(share_secret="corwin_has_locket"), None, Dice(1))
    assert "30 gold" in fx["shared"]
    assert any(e["kind"] == "lore" for e in g["journal"])


def test_persuasion_lowers_the_bar(at_tavern):
    g = at_tavern
    dialogue.start(g, "corwin", Dice(1))
    g["world"]["npcs"]["corwin"]["disposition"] = 50
    check = dialogue.social_check(g, "corwin", "persuade", ScriptedDice([18]))
    assert check["success"] and check["dc"] == 13
    fx = dialogue.apply_reply(g, "corwin", "come on", reply(share_secret="corwin_has_locket"), check, Dice(1))
    assert "shared" in fx


def test_bribe_costs_gold(at_tavern):
    g = at_tavern
    dialogue.start(g, "corwin", Dice(1))
    check = dialogue.social_check(g, "corwin", "bribe", Dice(1))
    assert g["player"]["gold"] == 7
    fx = dialogue.apply_reply(g, "corwin", "for you", reply(), check, Dice(1))
    assert fx["disposition"]["after"] == 45


def test_quest_offer_activates(at_tavern):
    g = at_tavern
    dialogue.start(g, "maren", Dice(1))
    fx = dialogue.apply_reply(g, "maren", "any work?", reply(offer_quest="wolves"), None, Dice(1))
    assert fx["quest_started"] == "The Ashwood Howls"
    assert g["world"]["quests"]["wolves"]["status"] == "active"
    # a quest the NPC doesn't own is ignored
    dialogue.apply_reply(g, "maren", "?", reply(offer_quest="nonsense"), None, Dice(1))


def test_turn_hostile_only_when_relationship_is_bad(at_tavern):
    g = at_tavern
    dialogue.start(g, "corwin", Dice(1))
    dialogue.apply_reply(g, "corwin", "thief", reply(turn_hostile=True, disposition_change=-5), None, Dice(1))
    assert g["mode"] == "dialogue"  # 30 is still above the threshold
    fx = dialogue.apply_reply(g, "corwin", "thief!", reply(turn_hostile=True, disposition_change=-10), None,
                              ScriptedDice([20, 1]))
    assert "fight" in fx and g["mode"] == "combat"
    assert g["world"]["npcs"]["corwin"]["hostile"]
    assert g["combat"]["combatants"]["e1"]["npc_id"] == "corwin"


def test_very_low_disposition_forces_a_fight(at_tavern):
    g = at_tavern
    dialogue.start(g, "corwin", Dice(1))
    g["world"]["npcs"]["corwin"]["disposition"] = 10
    dialogue.apply_reply(g, "corwin", "...", reply(disposition_change=-25), None, ScriptedDice([20, 1]))
    assert g["mode"] == "combat"


def test_killing_npc_drops_what_they_carry(at_tavern):
    from dungeon import combat
    g = at_tavern
    dialogue.start_fight(g, "corwin", ScriptedDice([20, 1]), "fight")
    g["combat"]["combatants"]["e1"]["hp"] = 1
    combat.player_action(g, "attack", ScriptedDice([15, 3, 4, 4]))
    assert state.inventory_count(g, "silver_locket") == 1
    assert not g["world"]["npcs"]["corwin"]["alive"]
    assert "corwin" not in state.location(g)["npcs"]


def test_trade_prices_and_stock(g):
    put_in(g, "smithy")
    dialogue.start(g, "brannoc", Dice(1))
    r = dialogue.trade(g, "buy", "healing potion")
    assert r["cost"] == 10 and g["player"]["gold"] == 2
    with pytest.raises(GameError):
        dialogue.trade(g, "buy", "firebomb")  # can't afford
    r = dialogue.trade(g, "sell", "old map")
    assert r["for"] == 1
    g["world"]["npcs"]["brannoc"]["disposition"] = 80
    assert dialogue.price(g, "brannoc", "iron_shield") == 16


def test_buying_the_locket_removes_it_from_stock(at_tavern):
    g = at_tavern
    g["player"]["gold"] = 100
    dialogue.start(g, "corwin", Dice(1))
    dialogue.trade(g, "buy", "locket")
    assert state.inventory_count(g, "silver_locket") == 1
    assert "silver_locket" not in dialogue.stock(g["world"]["npcs"]["corwin"])


def test_giving_locket_completes_quest(at_tavern):
    g = at_tavern
    state.add_item(g["player"]["inventory"], "silver_locket")
    r = dialogue.give(g, "maren", "locket")
    assert r["quests_turned_in"][0]["quest"] == "Maren's Locket"
    assert g["world"]["quests"]["locket"]["status"] == "done"
    assert g["player"]["gold"] == 12 + 15 and g["player"]["xp"] == 60
    assert g["world"]["npcs"]["maren"]["disposition"] == 75


def test_ready_quest_is_turned_in_when_you_talk(at_tavern):
    g = at_tavern
    g["world"]["quests"]["wolves"]["status"] = "ready"
    r = dialogue.start(g, "maren", Dice(1))
    assert r["quests_turned_in"][0]["gold"] == 25
    assert g["world"]["quests"]["wolves"]["status"] == "done"


def test_brief_hides_shared_secrets(at_tavern):
    g = at_tavern
    g["world"]["npcs"]["maren"]["shared"] = ["wolves_fire"]
    b = dialogue.brief(g, "maren")
    assert [s["id"] for s in b["secrets_you_could_share"]] == ["corwin_locket"]
