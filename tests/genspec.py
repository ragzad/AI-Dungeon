"""A small generated-style opening for tests: Creator output with no numbers in it."""
import copy

SPEC = {
    "setting_name": "Saltmarrow",
    "tone": "damp, hushed, salt-bitten",
    "blurb": "A cathedral town half under the tide. The bells still ring below the water.",
    "starting_weapon": {"name": "Barnacle Hook", "description": "A shell-crusted gaff.", "archetype": "light_weapon",
                        "tier": 3, "damage_type": "piercing"},
    "starting_consumable": {"name": "Brine Cordial", "description": "Salt and kelp, oddly warming.",
                            "archetype": "bomb", "tier": 2},
    "items": [
        {"name": "Tidewrack Mail", "description": "Chain gone green.", "archetype": "heavy_armour", "tier": 2},
        {"name": "Kelp Poultice", "description": "Slimy, soothing.", "archetype": "potion", "tier": 1},
        {"name": "Bell-Shard", "description": "Rings when you grip it.", "archetype": "trinket", "tier": 1, "bonus": "hit"},
    ],
    "monsters": [
        {"name": "Silt-Walker", "description": "A drowned pilgrim.", "archetype": "brute", "tier": 1,
         "damage_type": "bludgeoning", "weak": "radiant",
         "abilities": [{"name": "Waterlogged Grip", "description": "Cold hands.", "target": "enemy",
                        "blocks": [{"kind": "damage"}, {"kind": "status", "status": "weakened"}]}]},
        {"name": "Brine-Crab Swarm", "description": "Clicking shells.", "archetype": "swarm", "tier": 1,
         "damage_type": "piercing", "abilities": []},
        {"name": "The Sunken Prelate", "description": "Mitre crusted with coral.", "archetype": "boss", "tier": 3,
         "damage_type": "necrotic", "resist": "frost", "weak": "radiant",
         "abilities": [{"name": "Grave Summons", "description": "Calls the drowned.", "target": "self",
                        "blocks": [{"kind": "summon"}]}]},
    ],
    "start": {"name": "Bell-Tower Vestibule", "description": "Wet stone and a rope that hums.", "features": [], "items": []},
    "places": [
        {"direction": "north", "name": "The Drowned Nave", "description": "Pews under a foot of water.",
         "features": [], "items": [], "encounter": [{"monster": "Silt-Walker", "count": 2}],
         "encounter_text": "Shapes rise from the water.", "rest": False},
        {"direction": "east", "name": "Mallow's Cell", "description": "A dry room with a cot.",
         "features": [], "items": [], "encounter": [], "encounter_text": "", "rest": True},
    ],
    "npcs": [
        {"name": "Brother Mallow", "role": "librarian", "personality": "Fussy.", "voice": "Whispery.",
         "goals": ["Save the books"], "secret": "", "disposition": 50, "fights_as": "caster", "where": "start", "sells": []},
    ],
    "quest": {"title": "Quiet the Nave", "desc": "Put the walkers down.", "giver": "Brother Mallow",
              "kind": "defeat", "monster": "Silt-Walker"},
    "boss_lair": {"direction": "north", "approach_name": "The Flooded Crypt", "approach_description": "Bones float.",
                  "approach_encounter_text": "Something stirs.", "lair_name": "The Prelate's Font",
                  "lair_description": "A font that never stops filling.", "boss_intro": "The Prelate rises.",
                  "gate_text": "The water below is black and very cold.", "rumour": "They say the Prelate still says Mass under the nave.",
                  "quest_title": "Silence the Prelate"},
    "unexplored": [{"direction": "west", "hint": "a causeway into fog"}],
}


def spec():
    return copy.deepcopy(SPEC)
