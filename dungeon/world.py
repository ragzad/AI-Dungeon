"""Exploration rules: moving, looking, items. The old Archivist's job, done in code."""
from . import combat, content
from .state import (GameError, add_item, inventory_options, item_info, journal, location,
                    match, norm, npc, npcs_here, remove_item)

OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "up": "down", "down": "up", "in": "out", "out": "in"}
OFFSET = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
          "up": (0, -1), "down": (0, 1), "in": (0, -1), "out": (0, 1)}
DIRECTION_WORDS = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down",
                   "inside": "in", "outside": "out", "back": None}
DC = {"easy": 10, "medium": 13, "hard": 16, "very_hard": 19}


def describe(g):
    loc = location(g)
    exits = []
    for direction, dest in loc["exits"].items():
        if isinstance(dest, str):
            exits.append(f"{direction}: {g['world']['locations'][dest]['name']}")
        else:
            exits.append(f"{direction}: {dest.get('hint', 'somewhere unexplored')} (unexplored)")
    people = []
    for nid in loc["npcs"]:
        n = npc(g, nid)
        if n["alive"]:
            people.append(f"{n['name']} ({n['role']}{', hostile' if n['hostile'] else ''})")
    return {
        "location": loc["name"],
        "description": loc["desc"],
        "exits": exits,
        "people": people,
        "items_here": [item_info(i["id"])["name"] + (f" x{i['qty']}" if i["qty"] > 1 else "") for i in loc["items"]],
        "things_to_inspect": list(loc.get("features", {}).keys()),
        "mode": g["mode"],
    }


def _resolve_exit(g, direction):
    loc = location(g)
    word = norm(direction)
    if word in ("back", "go back") and g["meta"].get("prev_location_id"):
        for d, dest in loc["exits"].items():
            if dest == g["meta"]["prev_location_id"]:
                return d
    word = DIRECTION_WORDS.get(word, word)
    if word in loc["exits"]:
        return word
    names = {}
    for d, dest in loc["exits"].items():
        names[d] = g["world"]["locations"][dest]["name"] if isinstance(dest, str) else dest.get("hint", "")
    found = match(direction, names)
    if found:
        return found
    raise GameError(f"You can't go '{direction}' from here. Exits: {', '.join(loc['exits'])}.")


def move(g, direction, d):
    if g["mode"] == "combat":
        raise GameError("You can't just walk away from a fight. Flee if you want out.")
    if g["mode"] == "dead":
        raise GameError("You are dead.")
    left_dialogue = None
    if g["mode"] == "dialogue":
        left_dialogue = npc(g, g["dialogue"]["npc_id"])["name"]
    exit_dir = _resolve_exit(g, direction)
    dest = location(g)["exits"][exit_dir]
    if not isinstance(dest, str):
        return {"needs_creation": {"direction": exit_dir, "hint": dest.get("hint", "")}}
    if left_dialogue:
        end_dialogue(g)
    g["meta"]["prev_location_id"] = g["meta"]["location_id"]
    g["meta"]["location_id"] = dest
    g["meta"]["turn"] += 1
    loc = location(g)
    first_visit = not loc.get("visited")
    loc["visited"] = True
    if g["combat"] and g["combat"].get("outcome"):
        g["combat"] = None
    if first_visit:
        journal(g, f"Reached {loc['name']}.", "travel")
    result = {"moved": exit_dir, "first_visit": first_visit, **describe(g)}
    if left_dialogue:
        result["left_conversation_with"] = left_dialogue
    enc = loc.get("encounter")
    if enc:
        fight = combat.start_combat(g, [{"template": t} for t in enc["enemies"]], d, intro=enc.get("text"))
        result["encounter"] = {"text": enc.get("text"), "events": fight["events"], "status": combat.summary(g)}
    return result


def add_location(g, direction, spec):
    """Place a Creator-made location behind an unexplored exit. Validates everything."""
    here_id = g["meta"]["location_id"]
    here = location(g)
    dest = here["exits"].get(direction)
    if dest is None or isinstance(dest, str):
        raise GameError("That exit is already explored.")
    name = str(spec.get("name") or "").strip()[:60]
    desc = str(spec.get("description") or "").strip()[:600]
    if not name or not desc:
        raise GameError("The Creator didn't describe the place properly.")
    base = "loc_" + (norm(name).replace(" ", "_")[:30] or "place")
    new_id, n = base, 2
    while new_id in g["world"]["locations"]:
        new_id, n = f"{base}_{n}", n + 1
    dx, dy = OFFSET.get(direction, (0, 1))
    back = OPPOSITE.get(direction, "back")
    exits = {back: here_id}
    for e in (spec.get("exits") or [])[:3]:
        ed = norm(e.get("direction", ""))
        if ed in OFFSET and ed not in exits:
            exits[ed] = {"to": None, "hint": str(e.get("hint", "a way onward"))[:100]}
    features = {}
    for f in (spec.get("features") or [])[:3]:
        key = norm(f.get("name", ""))[:30]
        if key:
            features[key] = str(f.get("description", ""))[:300]
    items = [{"id": i, "qty": 1} for i in (spec.get("items") or [])[:2] if i in content.ITEMS]
    loc = {"name": name, "desc": desc, "x": here["x"] + dx, "y": here["y"] + dy,
           "exits": exits, "features": features, "items": items, "npcs": [], "created": True}
    enemies = [t for t in (spec.get("encounter") or [])[:2] if t in content.MONSTERS]
    if enemies:
        loc["encounter"] = {"enemies": enemies, "text": str(spec.get("encounter_text") or "Something moves in the gloom.")[:200]}
    new_npc = spec.get("npc")
    if new_npc and new_npc.get("name"):
        nid = "npc_" + norm(new_npc["name"]).replace(" ", "_")[:24]
        if nid not in g["world"]["npcs"]:
            g["world"]["npcs"][nid] = {
                "name": str(new_npc["name"])[:40], "role": str(new_npc.get("role", "stranger"))[:60],
                "location_id": new_id, "personality": str(new_npc.get("personality", ""))[:300],
                "voice": str(new_npc.get("voice", ""))[:120], "goals": [str(x)[:100] for x in new_npc.get("goals", [])[:3]],
                "secrets": [{"id": f"{nid}_secret", "text": str(new_npc.get("secret", ""))[:200], "min_disposition": 60}]
                if new_npc.get("secret") else [],
                "quests": [], "disposition": max(10, min(70, int(new_npc.get("disposition", 45)))),
                "memory": [], "hostile": False, "alive": True, "met": False,
                "trades": {"sells": [], "buys": False},
                "combat": {"template": new_npc.get("fights_as") if new_npc.get("fights_as") in content.MONSTERS else "bandit",
                           "name": str(new_npc["name"])[:40]},
            }
            loc["npcs"].append(nid)
    g["world"]["locations"][new_id] = loc
    here["exits"][direction] = new_id
    return new_id


def inspect(g, target):
    loc = location(g)
    t = norm(target)
    if not t or t in ("room", "around", "here", "area"):
        return describe(g)
    features = loc.get("features", {})
    fid = match(target, {k: k for k in features})
    if fid:
        return {"feature": fid, "detail": features[fid]}
    nid = match(target, npcs_here(g))
    if nid:
        n = npc(g, nid)
        from .state import attitude
        return {"person": n["name"], "role": n["role"], "seems": "hostile" if n["hostile"] else attitude(n["disposition"]),
                "met_before": n["met"]}
    here_items = {i["id"]: item_info(i["id"])["name"] for i in loc["items"]}
    iid = match(target, here_items) or match(target, inventory_options(g))
    if iid:
        info = item_info(iid)
        return {"item": info["name"], "detail": info["desc"]}
    raise GameError(f"You don't see any '{target}' here.")


def take(g, target):
    if g["mode"] == "combat":
        raise GameError("No time for that mid-fight.")
    loc = location(g)
    options = {i["id"]: item_info(i["id"])["name"] for i in loc["items"]}
    iid = match(target, options)
    if not iid:
        raise GameError(f"There's no '{target}' here to take.")
    qty = next(i["qty"] for i in loc["items"] if i["id"] == iid)
    remove_item(loc["items"], iid, qty)
    add_item(g["player"]["inventory"], iid, qty)
    g["meta"]["turn"] += 1
    return {"took": item_info(iid)["name"], "qty": qty}


def drop(g, target):
    iid = match(target, inventory_options(g))
    if not iid:
        raise GameError(f"You aren't carrying '{target}'.")
    if g["player"]["equipped"].get("weapon") == iid:
        g["player"]["equipped"]["weapon"] = None
    if g["player"]["equipped"].get("armour") == iid:
        g["player"]["equipped"]["armour"] = None
    remove_item(g["player"]["inventory"], iid)
    add_item(location(g)["items"], iid)
    return {"dropped": item_info(iid)["name"]}


def use_item(g, target, d):
    """Using things outside combat: drink, equip, read."""
    if g["mode"] == "combat":
        raise GameError("Use items in combat through the combat actions.")
    iid = match(target, inventory_options(g))
    if not iid:
        raise GameError(f"You aren't carrying '{target}'.")
    info = item_info(iid)
    p = g["player"]
    if info["kind"] == "weapon":
        p["equipped"]["weapon"] = iid
        return {"equipped": info["name"], "damage": info.get("damage")}
    if info["kind"] == "armour":
        p["equipped"]["armour"] = iid
        return {"equipped": info["name"]}
    effect = info.get("effect") or {}
    if info.get("combat_only"):
        raise GameError(f"Save the {info['name']} for a fight.")
    if "heal" in effect:
        if p["hp"] >= p["max_hp"]:
            raise GameError("You're already at full health.")
        remove_item(p["inventory"], iid)
        roll = d.roll(effect["heal"])
        healed = min(roll["total"], p["max_hp"] - p["hp"])
        p["hp"] += healed
        return {"used": info["name"], "healed": healed, "hp": p["hp"], "roll": roll["rolls"]}
    if "cure" in effect:
        remove_item(p["inventory"], iid)
        p["status"] = [s for s in p["status"] if s["name"] != effect["cure"]]
        return {"used": info["name"], "cured": effect["cure"]}
    return {"item": info["name"], "detail": info["desc"], "note": "Nothing happens beyond looking at it."}


def rest(g):
    loc = location(g)
    if g["mode"] != "exploration":
        raise GameError("You can't rest right now.")
    if not loc.get("rest"):
        raise GameError("This isn't a safe place to rest. Find an inn.")
    if any(npc(g, nid)["hostile"] and npc(g, nid)["alive"] for nid in loc["npcs"]):
        raise GameError("Not with someone hostile watching you.")
    p = g["player"]
    if p["gold"] < 5:
        raise GameError("A bed costs 5 gold and you can't afford it.")
    p["gold"] -= 5
    p["hp"] = p["max_hp"]
    p["status"] = []
    p["abilities"] = {k: v["max_uses"] for k, v in content.ABILITIES.items()}
    g["meta"]["turn"] += 4
    journal(g, f"Rested at {loc['name']}.", "rest")
    return {"rested": True, "hp": p["hp"], "gold_left": p["gold"]}


def skill_check(g, stat, difficulty, d, what=""):
    stat = norm(stat)[:3]
    if stat not in g["player"]["stats"]:
        raise GameError(f"Unknown stat '{stat}'. Use str, dex, con, int, wis or cha.")
    difficulty = norm(difficulty).replace(" ", "_")
    if difficulty == "impossible":
        return {"what": what, "success": False, "impossible": True}
    dc = DC.get(difficulty, 13)
    roll = d.d(20)
    mod = g["player"]["stats"][stat]
    g["meta"]["turn"] += 1
    return {"what": what, "stat": stat, "roll": roll, "modifier": mod, "total": roll + mod, "dc": dc,
            "success": roll + mod >= dc, "critical": roll in (1, 20)}


def end_dialogue(g):
    if g["mode"] == "dialogue":
        g["mode"] = "exploration"
        g["dialogue"] = None
