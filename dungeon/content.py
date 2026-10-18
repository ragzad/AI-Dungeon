"""Hand-written starting content. The Creator adds to this as you explore."""

ITEMS = {
    "healing_potion": {"name": "Healing Potion", "kind": "consumable", "price": 10,
                       "desc": "A stoppered vial of red cordial. Restores 2d4+2 HP.",
                       "effect": {"heal": "2d4+2"}},
    "firebomb": {"name": "Firebomb", "kind": "consumable", "price": 15, "combat_only": True,
                 "desc": "A clay pot of lamp oil and pitch. 2d6 fire damage and sets the target burning.",
                 "effect": {"damage": "2d6", "status": "burning"}},
    "antidote": {"name": "Antidote", "kind": "consumable", "price": 6,
                 "desc": "Bitter herbs in a twist of cloth. Cures poison.",
                 "effect": {"cure": "poisoned"}},
    "rusty_sword": {"name": "Rusty Sword", "kind": "weapon", "price": 6,
                    "desc": "Pitted, but it still holds an edge.", "damage": "1d8"},
    "fine_sword": {"name": "Brannoc's Longsword", "kind": "weapon", "price": 35,
                   "desc": "Fresh from the forge, balanced and keen.", "damage": "1d10"},
    "iron_shield": {"name": "Iron Shield", "kind": "armour", "price": 20,
                    "desc": "A dented round shield. +1 AC while equipped.", "ac": 1},
    "wolf_pelt": {"name": "Wolf Pelt", "kind": "loot", "price": 4,
                  "desc": "Grey fur, singed black at the tips."},
    "silver_locket": {"name": "Silver Locket", "kind": "quest", "price": 30,
                      "desc": "A tarnished locket with a lock of red hair inside. Engraved 'M.H.'"},
    "old_map": {"name": "Old Map", "kind": "misc", "price": 1,
                "desc": "A faded map of the Ashwood. Someone has circled a clearing to the south."},
    "lantern": {"name": "Lantern", "kind": "misc", "price": 3,
                "desc": "A hooded tin lantern, half full of oil."},
    "ember_shard": {"name": "Ember Shard", "kind": "loot", "price": 25,
                    "desc": "A splinter of stone that is warm to the touch and glows faintly."},
    "bone_charm": {"name": "Bone Charm", "kind": "loot", "price": 8,
                   "desc": "Knucklebones strung on gut. Someone made this to ward something off."},
}

# Enemies the engine knows how to run. The Creator can only place these, it
# can't make up stats.
MONSTERS = {
    "ash_wolf": {"name": "Ash Wolf", "hp": 9, "ac": 12, "attack": 3, "damage": "1d6+1", "dex": 2,
                 "ai": "brute", "xp": 25, "gold": "0d1", "loot": ["wolf_pelt"],
                 "ability": {"id": "savage_bite", "name": "Savage Bite", "uses": 1,
                             "damage": "1d6+1", "status": "bleeding"}},
    "bandit": {"name": "Bandit", "hp": 16, "ac": 13, "attack": 4, "damage": "1d6+2", "dex": 3,
               "ai": "cunning", "xp": 50, "gold": "2d6", "loot": [],
               "ability": {"id": "poisoned_blade", "name": "Poisoned Blade", "uses": 1,
                           "damage": "1d4+2", "status": "poisoned"}},
    "cinder_ghoul": {"name": "Cinder Ghoul", "hp": 18, "ac": 11, "attack": 3, "damage": "1d8", "dex": 0,
                     "ai": "brute", "xp": 45, "gold": "1d4", "loot": ["bone_charm"],
                     "ability": {"id": "smother", "name": "Smothering Ash", "uses": 1,
                                 "damage": "1d4", "status": "stunned"}},
    "ember_wisp": {"name": "Ember Wisp", "hp": 8, "ac": 14, "attack": 5, "damage": "1d4+2", "dex": 4,
                   "ai": "cunning", "xp": 30, "gold": "0d1", "loot": ["ember_shard"],
                   "ability": {"id": "flare", "name": "Flare", "uses": 1,
                               "damage": "1d6", "status": "burning"}},
}

STATUS = {
    "poisoned": {"turns": 3, "damage": "1d4", "desc": "takes 1d4 poison damage each turn"},
    "burning": {"turns": 2, "damage": "1d6", "desc": "takes 1d6 fire damage each turn"},
    "bleeding": {"turns": 2, "damage": "1d3", "desc": "takes 1d3 damage each turn"},
    "stunned": {"turns": 1, "desc": "loses their next turn"},
    "defending": {"turns": 1, "ac": 2, "desc": "+2 AC until their next turn"},
}

ABILITIES = {
    "power_strike": {"name": "Power Strike", "max_uses": 2,
                     "desc": "A heavy swing: -2 to hit, +1d6 damage."},
    "second_wind": {"name": "Second Wind", "max_uses": 1,
                    "desc": "Catch your breath and heal 1d10 + level."},
}


def new_player(name="Wren"):
    return {
        "name": name or "Wren",
        "class": "Sellsword",
        "level": 1,
        "xp": 0,
        "xp_next": 100,
        "hp": 30,
        "max_hp": 30,
        "base_ac": 12,
        "stats": {"str": 3, "dex": 2, "con": 2, "int": 0, "wis": 1, "cha": 1},
        "proficiency": 2,
        "gold": 12,
        "inventory": [
            {"id": "rusty_sword", "qty": 1},
            {"id": "healing_potion", "qty": 2},
            {"id": "old_map", "qty": 1},
        ],
        "equipped": {"weapon": "rusty_sword", "armour": None},
        "abilities": {k: v["max_uses"] for k, v in ABILITIES.items()},
        "status": [],
    }


def new_world():
    locations = {
        "square": {
            "name": "Emberfall Square",
            "desc": ("A muddy square ringed by crooked timber houses. Ash drifts down from the "
                     "forest to the south like grey snow, and the well in the middle has a "
                     "bucket chained to it."),
            "x": 0, "y": 0,
            "exits": {"north": "tavern", "east": "smithy", "south": "ashwood_edge",
                      "west": {"to": None, "hint": "a sunken lane towards the old chapel"}},
            "features": {"well": "The water smells of smoke. Someone has scratched 'NOT AGAIN' into the stone."},
            "items": [{"id": "lantern", "qty": 1}],
            "npcs": [],
        },
        "tavern": {
            "name": "The Gutter Lantern",
            "desc": ("A low, warm taproom that smells of peat smoke and spilled ale. A notice board "
                     "by the door is crowded with pinned scraps."),
            "x": 0, "y": -1, "rest": True,
            "exits": {"south": "square"},
            "features": {"notice board": "Most notices are about the wolves. One reads: 'LOST: silver locket. Reward. Ask Maren.'",
                         "fire": "A peat fire, banked high. A cat sleeps in front of it."},
            "items": [],
            "npcs": ["maren", "corwin"],
        },
        "smithy": {
            "name": "Brannoc's Forge",
            "desc": "An open-fronted forge glowing orange. Tools hang from every beam.",
            "x": 1, "y": 0,
            "exits": {"west": "square"},
            "features": {"anvil": "Scarred with years of work. A half-finished blade lies across it."},
            "items": [],
            "npcs": ["brannoc"],
        },
        "ashwood_edge": {
            "name": "Ashwood Edge",
            "desc": ("Burnt pines stand like black spears where the village gives way to forest. "
                     "Fresh tracks press into the ash, big ones."),
            "x": 0, "y": 1, "danger": 1,
            "exits": {"north": "square",
                      "south": {"to": None, "hint": "deeper into the Ashwood, where the trees are burned black"}},
            "features": {"tracks": "Wolf tracks, at least two animals, circling the same spot again and again."},
            "items": [],
            "npcs": [],
            "encounter": {"enemies": ["ash_wolf", "ash_wolf"], "text": "Two ash-grey wolves slink out from behind the pines."},
        },
    }
    npcs = {
        "maren": {
            "name": "Maren Holt", "role": "innkeeper of the Gutter Lantern", "location_id": "tavern",
            "personality": "Warm, quick-witted and shrewd. Lost her husband to the forest two winters ago and won't be pitied.",
            "voice": "Brisk local dialect, calls people 'love', dry humour.",
            "goals": ["Keep the inn going", "Get her late husband's locket back", "Stop the wolves taking the supply carts"],
            "secrets": [
                {"id": "corwin_locket", "text": "She saw Corwin Vane admiring a silver locket that looks like the one she lost.", "min_disposition": 55},
                {"id": "wolves_fire", "text": "The wolves only started coming out after the fire in the Ashwood, as if something drove them.", "min_disposition": 40},
            ],
            "quests": ["wolves", "locket"],
            "disposition": 55, "memory": [], "hostile": False, "alive": True, "met": False,
            "trades": {"sells": ["healing_potion"], "buys": False},
            "combat": {"template": "bandit", "name": "Maren Holt", "hp": 14},
        },
        "corwin": {
            "name": "Corwin Vane", "role": "card sharp and petty thief", "location_id": "tavern",
            "personality": "Charming on the surface, prickly and proud underneath. Hates being called a thief. Quick to draw a knife if cornered.",
            "voice": "Smooth, theatrical, a bit too polite.",
            "goals": ["Win enough at cards to leave Emberfall", "Keep the locket he stole", "Avoid the watch"],
            "secrets": [
                {"id": "corwin_has_locket", "text": "He took the silver locket from Maren's room and will sell it for 30 gold.", "min_disposition": 65},
                {"id": "chapel_cache", "text": "Smugglers hide goods under the old chapel to the west.", "min_disposition": 70},
            ],
            "quests": [],
            "disposition": 35, "memory": [], "hostile": False, "alive": True, "met": False,
            "trades": {"sells": ["silver_locket", "antidote"], "buys": True},
            "carries": [{"id": "silver_locket", "qty": 1}],
            "combat": {"template": "bandit", "name": "Corwin Vane"},
        },
        "brannoc": {
            "name": "Brannoc", "role": "village smith", "location_id": "smithy",
            "personality": "Gruff, honest, few words. Respects people who pay fairly and hates haggling.",
            "voice": "Short sentences. Grunts. Very occasional dark joke.",
            "goals": ["Sell enough to buy coal for winter", "Find out what is burning in the Ashwood"],
            "secrets": [
                {"id": "ember_ore", "text": "The stones from deep in the Ashwood stay warm for days. He thinks something under the forest is still burning.", "min_disposition": 60},
            ],
            "quests": [],
            "disposition": 50, "memory": [], "hostile": False, "alive": True, "met": False,
            "trades": {"sells": ["healing_potion", "firebomb", "iron_shield", "fine_sword", "antidote"], "buys": True},
            "combat": {"template": "bandit", "name": "Brannoc", "hp": 24, "ac": 14},
        },
    }
    quests = {
        "wolves": {"title": "The Ashwood Howls", "giver": "maren", "status": "available",
                   "desc": "Wolves at the Ashwood Edge have been taking the supply carts. Deal with them.",
                   "goal": {"type": "defeat", "template": "ash_wolf", "count": 2},
                   "progress": 0, "reward": {"gold": 25, "xp": 50}},
        "locket": {"title": "Maren's Locket", "giver": "maren", "status": "available",
                   "desc": "Find the silver locket Maren lost and bring it back to her.",
                   "goal": {"type": "deliver", "item": "silver_locket", "to": "maren"},
                   "progress": 0, "reward": {"gold": 15, "xp": 60, "disposition": 20}},
    }
    return {"locations": locations, "npcs": npcs, "quests": quests}
