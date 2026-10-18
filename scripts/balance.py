"""Balance check: random but valid Creator output, fought through the real engine with sensible play.

    python scripts/balance.py [worlds] [seeds]
"""
import copy
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dungeon import combat, content, forge, premise, state
from dungeon.dice import Dice

TYPES = list(content.DAMAGE_TYPES)


def rand_ability(r, owner):
    target = r.choice(["enemy", "enemy", "all_enemies", "self"])
    if target == "self":
        kinds = r.sample(["heal", "shield", "status", "cure"] + (["summon"] if owner == "monster" else []), r.randint(1, 2))
    else:
        kinds = r.sample(["damage", "status", "push", "chain"], r.randint(1, 3))
    blocks = []
    for k in kinds:
        b = {"kind": k}
        if k in ("damage", "chain"):
            b["damage_type"] = r.choice(TYPES)
        if k == "status":
            b["status"] = r.choice(forge.GOOD if target == "self" else forge.BAD)
        blocks.append(b)
    return {"name": f"Move {r.randint(0, 9999)}", "description": "x", "target": target, "blocks": blocks}


def rand_monster(r, i, tier, arch=None):
    arch = arch or r.choice([a for a in forge.MONSTER_ARCHETYPES if a != "boss"])
    weak = r.choice(TYPES + [None])
    return {"name": f"Beast {i}", "archetype": arch, "tier": tier, "damage_type": r.choice(TYPES),
            "resist": r.choice(TYPES[3:] + [None]), "weak": weak,
            "abilities": [rand_ability(r, "monster") for _ in range(r.randint(1, 2))], "loot": []}


def rand_item(r, i):
    arch = r.choice(list(forge.ITEM_ARCHETYPES))
    it = {"name": f"Thing {i}", "description": "x", "archetype": arch, "tier": r.randint(1, 3),
          "damage_type": r.choice(TYPES), "on_hit_status": r.choice(list(forge.ON_HIT) + [None]),
          "resist": r.choice(TYPES), "bonus": r.choice(["hit", "ac", "max_hp", "resist"])}
    if arch in ("bomb", "tonic", "scroll"):
        it["use"] = rand_ability(r, "player")
    return it


def rand_spec(seed):
    r = random.Random(seed)
    mons = [rand_monster(r, i, 1) for i in range(3)] + [rand_monster(r, 3, 2), rand_monster(r, 4, 3),
                                                        rand_monster(r, 5, 2, "boss")]
    places = []
    for j, d in enumerate(["north", "east", "south"]):
        enc = []
        if j < 2:
            m = mons[j]
            enc = [{"monster": m["name"], "count": 3 if m["archetype"] == "swarm" else r.randint(1, 2)}]
        places.append({"direction": d, "name": f"Place {j}", "description": "x", "features": [], "items": [],
                       "encounter": enc, "encounter_text": "!", "rest": j == 2})
    starter = {"name": "Starter", "description": "x", "archetype": r.choice(["light_weapon", "heavy_weapon", "ranged", "focus"]),
               "tier": 1, "damage_type": r.choice(TYPES), "on_hit_status": r.choice(list(forge.ON_HIT) + [None])}
    items = [rand_item(r, i) for i in range(6)] + [{"name": "Red Draught", "description": "x", "archetype": "potion", "tier": 1}]
    return {"setting_name": "Sim", "tone": "x", "blurb": "x", "starting_weapon": starter, "items": items,
            "monsters": mons, "start": {"name": "Start", "description": "x", "features": [], "items": []},
            "places": places, "npcs": [{"name": "Giver", "role": "x", "personality": "x", "voice": "x", "goals": [],
                                        "secret": "", "disposition": 50, "fights_as": "brute", "where": "start", "sells": []}],
            "quest": {"title": "Q", "desc": "x", "giver": "Giver", "kind": "defeat", "monster": mons[0]["name"],
                      "reward_ability": rand_ability(r, "player")},
            "unexplored": [{"direction": "west", "hint": "x"}]}


def choose(g):
    p, cb = g["player"], g["combat"]
    enemies = {k: c for k, c in cb["combatants"].items() if c["side"] == "enemy" and c["hp"] > 0}
    dtype = state.weapon_type(g)
    tid = min(enemies, key=lambda k: (0 if dtype in enemies[k].get("weak", []) else 1, enemies[k]["hp"]))
    low = p["hp"] <= p["max_hp"] * 0.4
    heals = [i["id"] for i in p["inventory"] if (state.item_info(i["id"], g).get("effect") or {}).get("heal")
             or any(b["kind"] == "heal" for b in (state.item_info(i["id"], g).get("use") or {}).get("blocks", []))]
    if low and heals:
        return dict(action="item", item=heals[0], target=tid)
    if low and p["abilities"].get("second_wind"):
        return dict(action="second_wind")
    learned = [k for k, v in p["abilities"].items() if v > 0 and k not in content.ABILITIES]
    for k in learned:
        a = state.ability_info(k, g)
        if a["target"] == "self" and low and any(b["kind"] in ("heal", "shield") for b in a["blocks"]):
            return dict(action="ability", ability=k)
        if a["target"] == "all_enemies" and len(enemies) >= 2:
            return dict(action="ability", ability=k, target=tid)
        if a["target"] == "enemy" and enemies[tid]["hp"] > 5:
            return dict(action="ability", ability=k, target=tid)
    bombs = [i["id"] for i in p["inventory"] if state.item_info(i["id"], g).get("combat_only")]
    if bombs and (len(enemies) >= 2 or enemies[tid]["hp"] > 12):
        return dict(action="item", item=bombs[0], target=tid)
    if p["abilities"].get("power_strike") and enemies[tid]["hp"] > 7:
        return dict(action="power_strike", target=tid)
    return dict(action="attack", target=tid)


def fight(g, enemies, seed, learn_reward=False):
    g = copy.deepcopy(g)
    g["meta"]["rng"] = {"seed": seed, "count": 0}
    if learn_reward:
        for q in g["world"]["quests"].values():
            if q["reward"].get("ability"):
                state.learn(g, q["reward"]["ability"])
    d = state.dice(g)
    combat.start_combat(g, [{"template": t} for t in enemies], d)
    for _ in range(80):
        if g["combat"]["outcome"]:
            break
        a = choose(g)
        try:
            combat.player_action(g, a.pop("action"), d, **a)
        except state.GameError:
            combat.player_action(g, "attack", d)
    return g["combat"]["outcome"], g["player"]["hp"]


def level_up(g, level, gear_tier=0):
    while g["player"]["level"] < level:
        combat.gain_xp(g, g["player"]["xp_next"] - g["player"]["xp"])
    # a sensible player has picked up or bought some of the world's gear by now
    if gear_tier:
        p = g["player"]
        for slot in ("weapon", "armour", "shield"):
            best = None
            for iid, it in g["world"]["items"].items():
                if it.get("slot") == slot and it["tier"] <= gear_tier:
                    score = it.get("ac", 0) * 3 if slot != "weapon" else sum(map(int, it["damage"].split("d")[1:])) // 2 + it.get("hit", 0)
                    if not best or score > best[0]:
                        best = (score, iid)
            if best:
                state.add_item(p["inventory"], best[1])
                p["equipped"][slot] = best[1]
    g["player"]["hp"] = g["player"]["max_hp"]


def run(worlds=40, seeds=25):
    rows = {"t1 opening @L1": [], "t1 opening @L1 +reward": [], "t2 pair @L2": [], "t3 pair @L3": [], "boss @L3": []}
    for w in range(worlds):
        g = premise.apply(state.new_game("Sim", seed=w), "sim", rand_spec(w))
        world = g["world"]
        encs = [l["encounter"]["enemies"] for l in world["locations"].values() if l.get("encounter")]
        mons = world["monsters"]
        t2 = [k for k, m in mons.items() if m["tier"] == 2 and m["archetype"] != "boss" and not m.get("npc")]
        t3 = [k for k, m in mons.items() if m["tier"] == 3 and m["archetype"] != "boss"]
        boss = [k for k, m in mons.items() if m["archetype"] == "boss"]
        for s in range(seeds):
            for e in encs:
                rows["t1 opening @L1"].append(fight(g, e, s)[0] == "victory")
                rows["t1 opening @L1 +reward"].append(fight(g, e, s, True)[0] == "victory")
            g2 = copy.deepcopy(g); level_up(g2, 2, 1)
            for k in t2:
                t1 = [x for x, m in mons.items() if m["tier"] == 1 and not m.get("npc")]
                pair = forge.fit_encounter([(k, mons[k])] * 2 + [(t1[s % len(t1)], mons[t1[s % len(t1)]])] * 2,
                                           forge.ENCOUNTER_BUDGET[2], 2)
                rows["t2 pair @L2"].append(fight(g2, pair, s, True)[0] == "victory")
            g3 = copy.deepcopy(g); level_up(g3, 3, 2)
            gb4 = copy.deepcopy(g); level_up(gb4, 4, 3)
            for k in t3:
                lower = [x for x, m in mons.items() if m["tier"] == 2 and m["archetype"] != "boss" and not m.get("npc")]
                pair = forge.fit_encounter([(k, mons[k])] * 2 + [(x, mons[x]) for x in lower[:1]] * 2,
                                           forge.ENCOUNTER_BUDGET[3], 3)
                rows["t3 pair @L3"].append(fight(g3, pair, s, True)[0] == "victory")
            for k in boss:
                lvl = 3 if mons[k]["tier"] == 2 else 4
                gb = g3 if lvl == 3 else gb4
                rows["boss @L3"].append(fight(gb, [k], s, True)[0] == "victory")
    base = []
    for s in range(seeds * 16):
        g = state.new_game("Sim", seed=s)
        base.append(fight(g, ["ash_wolf", "ash_wolf"], s)[0] == "victory")
    rows = {"emberfall wolves @L1": base, **rows}
    return {k: (sum(v) / max(1, len(v)), len(v)) for k, v in rows.items()}


if __name__ == "__main__":
    for k, (rate, n) in run(*(int(x) for x in sys.argv[1:])).items():
        print(f"{k:28s} {100 * rate:5.1f}%  (n={n})")
