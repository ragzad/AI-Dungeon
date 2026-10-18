"""Turns the player's story premise into a starting world.

The Creator writes the opening (places, people, a quest hook) and this checks
it against what the engine can actually run before anything goes in the save."""
import re

from . import content, forge
from .state import GameError, item_info, monster_info, norm

MAX_PREMISE = 300
COMPASS = ("north", "east", "south", "west")
OFFSET = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}

DEFAULT_SETTING = ("a dark fantasy adventure set in Emberfall, a village at the edge of the burnt Ashwood. "
                   "Something under the forest is still burning, which drove the wolves out")


def clean(text):
    """Tidy a premise from the start screen. Empty means keep the usual world."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_PREMISE]
    if text.lower().rstrip(".!") in ("", "surprise me"):
        return None
    return text


def setting_text(g):
    """One paragraph the agents get so they stay in the right world."""
    s = (g.get("meta") or {}).get("setting")
    if not s:
        return DEFAULT_SETTING
    return (f"{s['name']}. The player asked for this story: \"{s['premise']}\". {s['blurb']} "
            f"Tone: {s['tone']}.")


def _s(value, limit, default=""):
    return str(value or default).strip()[:limit]


def _features(spec):
    out = {}
    for f in (spec.get("features") or [])[:3]:
        key = norm(f.get("name", ""))[:30]
        if key:
            out[key] = _s(f.get("description"), 300)
    return out


def _slug(prefix, name, taken):
    base = prefix + (norm(name).replace(" ", "_")[:28] or "x")
    out, n = base, 2
    while out in taken:
        out, n = f"{base}_{n}", n + 1
    return out


def _foes(world, place, names, budget, max_tier):
    """Turn a place's encounter list into monster ids that fit the budget and tier."""
    picked = []
    for e in (place.get("encounter") or [])[:3]:
        if isinstance(e, str):
            ref, count = e, 1
        else:
            ref, count = e.get("monster") or e.get("template") or "", e.get("count") or 1
        mid = forge.resolve_monster(world, ref, names)
        if not mid:
            continue
        m = monster_info(mid, {"world": world})
        if m.get("tier", 1) > max_tier:
            continue
        count = max(1, min(3 if m.get("archetype") == "swarm" else 2, int(count)))
        override = _s(e.get("name"), 40) if isinstance(e, dict) else ""
        picked += [(mid, m, override)] * count
    kept = forge.fit_encounter([(mid, m) for mid, m, _ in picked], budget, max_tier)
    names_out = []
    for mid in kept:
        hit = next(x for x in picked if x[0] == mid)
        names_out.append(hit[2] or hit[1]["name"])
    return kept, names_out


def _encounter(world, place, names, budget=forge.ENCOUNTER_BUDGET[1], max_tier=1):
    kept, names_out = _foes(world, place, names, budget, max_tier)
    if not kept:
        return None
    return {"enemies": kept, "names": names_out,
            "text": _s(place.get("encounter_text"), 200, "Something moves in the gloom.")}


def _npc_template(world, n, nid, names):
    ref = n.get("fights_as") or ""
    mid = forge.resolve_monster(world, ref, names)
    if mid and monster_info(mid, {"world": world}).get("archetype") != "boss":
        return mid
    arch = ref if ref in forge.MONSTER_ARCHETYPES and ref != "boss" else None
    if not arch:
        return "bandit"
    world.setdefault("monsters", {})
    world.setdefault("abilities", {})
    tid, m = forge.make_monster({"name": n.get("name"), "archetype": arch, "tier": 1,
                                 "abilities": n.get("abilities") or []}, 1, taken=world["monsters"])
    m["npc"] = True
    world["monsters"][tid] = m
    return tid


def build_world(spec):
    """Validate a Creator opening and return (world, setting, kit). Raises GameError if unusable."""
    start = spec.get("start") or {}
    name, desc = _s(start.get("name"), 60), _s(start.get("description"), 600)
    if not name or not desc:
        raise GameError("The opening had no starting place.")
    world = {"locations": {}, "npcs": {}, "quests": {}}
    item_names, monster_names = forge.register(world, spec.get("items") or [], spec.get("monsters") or [])
    gen = {"world": world}

    def items_at(refs, max_tier=1):
        out = []
        for ref in (refs or [])[:2]:
            iid = forge.resolve_item(world, ref, item_names)
            if iid and item_info(iid, gen).get("kind") != "quest" and item_info(iid, gen).get("tier", 1) <= max_tier:
                out.append({"id": iid, "qty": 1})
        return out

    locations = world["locations"]
    locations["start"] = {"name": name, "desc": desc, "x": 0, "y": 0, "exits": {}, "features": _features(start),
                          "items": items_at(start.get("items")), "npcs": [], "visited": True}
    by_dir = {}
    for p in (spec.get("places") or [])[:3]:
        direction = norm(p.get("direction", ""))
        pname, pdesc = _s(p.get("name"), 60), _s(p.get("description"), 600)
        if direction not in OFFSET or direction in by_dir or not pname or not pdesc:
            continue
        lid = _slug("loc_", pname, locations)
        dx, dy = OFFSET[direction]
        loc = {"name": pname, "desc": pdesc, "x": dx, "y": dy, "exits": {OPPOSITE[direction]: "start"},
               "features": _features(p), "items": items_at(p.get("items")), "npcs": []}
        enc = _encounter(world, p, monster_names)
        if enc:
            loc["encounter"] = enc
            loc["danger"] = 1
        if p.get("rest"):
            loc["rest"] = True
        locations[lid] = loc
        locations["start"]["exits"][direction] = lid
        by_dir[direction] = lid
    if not by_dir:
        raise GameError("The opening had nowhere to go.")
    if not any(l.get("rest") for l in locations.values()):
        locations["start"]["rest"] = True

    npcs = world["npcs"]
    for n in (spec.get("npcs") or [])[:3]:
        nname = _s(n.get("name"), 40)
        if not nname:
            continue
        nid = _slug("npc_", nname, npcs)
        where = by_dir.get(norm(n.get("where", "")), "start")
        sells = []
        for ref in (n.get("sells") or [])[:5]:
            iid = forge.resolve_item(world, ref, item_names)
            if iid and item_info(iid, gen)["kind"] not in ("quest",) and item_info(iid, gen).get("tier", 1) <= 2:
                sells.append(iid)
        npcs[nid] = {
            "name": nname, "role": _s(n.get("role"), 60, "local"), "location_id": where,
            "personality": _s(n.get("personality"), 300), "voice": _s(n.get("voice"), 120),
            "goals": [_s(x, 100) for x in (n.get("goals") or [])[:3]],
            "secrets": [{"id": f"{nid}_secret", "text": _s(n.get("secret"), 200), "min_disposition": 55}]
            if n.get("secret") else [],
            "quests": [], "disposition": max(15, min(70, int(n.get("disposition") or 45))),
            "memory": [], "hostile": False, "alive": True, "met": False,
            "trades": {"sells": sells, "buys": bool(sells)},
            "combat": {"template": _npc_template(world, n, nid, monster_names), "name": nname},
        }
        locations[where]["npcs"].append(nid)
    if not npcs:
        raise GameError("The opening had nobody in it.")

    hook = spec.get("quest") or {}
    giver = next((nid for nid, n in npcs.items() if norm(n["name"]) == norm(hook.get("giver", ""))), next(iter(npcs)))
    npcs[giver]["disposition"] = max(npcs[giver]["disposition"], 45)
    title = _s(hook.get("title"), 60)
    if title:
        q = {"title": title, "giver": giver, "status": "available", "desc": _s(hook.get("desc"), 300),
             "progress": 0, "reward": {"gold": 25, "xp": 60}}
        item = forge.resolve_item(world, hook.get("item") or "", item_names)
        if hook.get("kind") == "find" and item:
            q["goal"] = {"type": "deliver", "item": item, "to": giver}
            # make sure the thing can actually be found
            if not any(i["id"] == item for l in locations.values() for i in l["items"]):
                locations[next(iter(by_dir.values()))]["items"].append({"id": item, "qty": 1})
        else:
            template = forge.resolve_monster(world, hook.get("monster") or "", monster_names)
            fights = [(lid, l["encounter"]) for lid, l in locations.items() if l.get("encounter")]
            m = monster_info(template, gen) if template else None
            if not m or m.get("tier", 1) > 1:
                template = fights[0][1]["enemies"][0] if fights else None
            if not template:
                template = next((k for k, v in world["monsters"].items() if v["tier"] == 1 and not v.get("npc")), "bandit")
            count = sum(e["enemies"].count(template) for _, e in fights)
            if not count:
                # the hook names a foe nobody placed, so put them somewhere
                target = next((lid for lid in by_dir.values() if not locations[lid].get("encounter")),
                              next(iter(by_dir.values())))
                mname = monster_info(template, gen)["name"]
                locations[target]["encounter"] = {"enemies": [template], "names": [mname],
                                                  "text": "Someone is waiting for you."}
                locations[target]["danger"] = 1
                count = 1
            q["goal"] = {"type": "defeat", "template": template, "count": count}
        if hook.get("reward_ability"):
            ab = forge.make_ability(hook["reward_ability"], 1, owner="player", taken=world["abilities"])
            world["abilities"][ab["id"]] = ab
            q["reward"]["ability"] = ab["id"]
        world["quests"]["hook"] = q
        npcs[giver]["quests"].append("hook")

    # leave the lazy Creator some room to grow the map
    for hint in (spec.get("unexplored") or [])[:2]:
        direction = norm(hint.get("direction", ""))
        if direction in OFFSET and direction not in locations["start"]["exits"]:
            locations["start"]["exits"][direction] = {"to": None, "hint": _s(hint.get("hint"), 100, "a way onward")}
    if len(locations["start"]["exits"]) < 4 and not any(isinstance(v, dict) for v in locations["start"]["exits"].values()):
        free = next(d for d in COMPASS if d not in locations["start"]["exits"])
        locations["start"]["exits"][free] = {"to": None, "hint": "a road leading somewhere you haven't been"}

    # a starting weapon and potion of the world's own, if the Creator made them
    kit = {}
    starter = spec.get("starting_weapon")
    if isinstance(starter, dict):
        sid, sw, _ = forge.make_item({**starter, "tier": 1}, 1, taken=world["items"])
        if sw and sw["kind"] == "weapon":
            world["items"][sid] = sw
            kit["weapon"] = sid
    kit["potion"] = next((k for k, v in world["items"].items() if v.get("archetype") == "potion" and v["tier"] == 1), None)

    setting = {"name": _s(spec.get("setting_name"), 60, name), "tone": _s(spec.get("tone"), 120, "grounded"),
               "blurb": _s(spec.get("blurb"), 400)}
    return world, setting, kit


def apply(g, premise, spec):
    """Swap a fresh game's world for one built from the premise."""
    world, setting, kit = build_world(spec)
    g["world"] = world
    g["meta"]["location_id"] = "start"
    g["meta"]["setting"] = {"premise": premise, **setting}
    p = g["player"]
    # the old map is a map of the Ashwood, which doesn't exist here
    inv = [i for i in p["inventory"] if i["id"] != "old_map"] + [{"id": "lantern", "qty": 1}]
    if kit.get("weapon"):
        inv = [i for i in inv if i["id"] != "rusty_sword"] + [{"id": kit["weapon"], "qty": 1}]
        p["equipped"]["weapon"] = kit["weapon"]
    if kit.get("potion"):
        inv = [i for i in inv if i["id"] != "healing_potion"] + [{"id": kit["potion"], "qty": 2}]
    p["inventory"] = inv
    return g
