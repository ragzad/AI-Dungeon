"""Turns the player's story premise into a starting world.

The Creator writes the opening (places, people, a quest hook) and this checks
it against what the engine can actually run before anything goes in the save."""
import re

from . import content
from .state import GameError, norm

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


def _encounter(place):
    foes = []
    for e in (place.get("encounter") or [])[:2]:
        t = e.get("template") if isinstance(e, dict) else e
        if t in content.MONSTERS:
            foes.append((t, _s(e.get("name") if isinstance(e, dict) else None, 40) or content.MONSTERS[t]["name"]))
    if not foes:
        return None
    return {"enemies": [t for t, _ in foes], "names": [n for _, n in foes],
            "text": _s(place.get("encounter_text"), 200, "Something moves in the gloom.")}


def build_world(spec):
    """Validate a Creator opening and return (world, setting). Raises GameError if unusable."""
    start = spec.get("start") or {}
    name, desc = _s(start.get("name"), 60), _s(start.get("description"), 600)
    if not name or not desc:
        raise GameError("The opening had no starting place.")
    locations = {"start": {"name": name, "desc": desc, "x": 0, "y": 0, "exits": {},
                           "features": _features(start),
                           "items": [{"id": i, "qty": 1} for i in (start.get("items") or [])[:2] if i in content.ITEMS],
                           "npcs": [], "visited": True}}
    by_dir = {}
    for p in (spec.get("places") or [])[:3]:
        direction = norm(p.get("direction", ""))
        pname, pdesc = _s(p.get("name"), 60), _s(p.get("description"), 600)
        if direction not in OFFSET or direction in by_dir or not pname or not pdesc:
            continue
        lid = _slug("loc_", pname, locations)
        dx, dy = OFFSET[direction]
        loc = {"name": pname, "desc": pdesc, "x": dx, "y": dy, "exits": {OPPOSITE[direction]: "start"},
               "features": _features(p),
               "items": [{"id": i, "qty": 1} for i in (p.get("items") or [])[:2] if i in content.ITEMS],
               "npcs": []}
        enc = _encounter(p)
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

    npcs = {}
    for n in (spec.get("npcs") or [])[:3]:
        nname = _s(n.get("name"), 40)
        if not nname:
            continue
        nid = _slug("npc_", nname, npcs)
        where = by_dir.get(norm(n.get("where", "")), "start")
        sells = [i for i in (n.get("sells") or [])[:4] if i in content.ITEMS and content.ITEMS[i]["kind"] != "quest"]
        npcs[nid] = {
            "name": nname, "role": _s(n.get("role"), 60, "local"), "location_id": where,
            "personality": _s(n.get("personality"), 300), "voice": _s(n.get("voice"), 120),
            "goals": [_s(x, 100) for x in (n.get("goals") or [])[:3]],
            "secrets": [{"id": f"{nid}_secret", "text": _s(n.get("secret"), 200), "min_disposition": 55}]
            if n.get("secret") else [],
            "quests": [], "disposition": max(15, min(70, int(n.get("disposition") or 45))),
            "memory": [], "hostile": False, "alive": True, "met": False,
            "trades": {"sells": sells, "buys": bool(sells)},
            "combat": {"template": n.get("fights_as") if n.get("fights_as") in content.MONSTERS else "bandit",
                       "name": nname},
        }
        locations[where]["npcs"].append(nid)
    if not npcs:
        raise GameError("The opening had nobody in it.")

    quests = {}
    hook = spec.get("quest") or {}
    giver = next((nid for nid, n in npcs.items() if norm(n["name"]) == norm(hook.get("giver", ""))), next(iter(npcs)))
    npcs[giver]["disposition"] = max(npcs[giver]["disposition"], 45)
    title = _s(hook.get("title"), 60)
    if title:
        q = {"title": title, "giver": giver, "status": "available", "desc": _s(hook.get("desc"), 300),
             "progress": 0, "reward": {"gold": 25, "xp": 60}}
        item = hook.get("item")
        if hook.get("kind") == "find" and item in content.ITEMS:
            q["goal"] = {"type": "deliver", "item": item, "to": giver}
            # make sure the thing can actually be found
            if not any(i["id"] == item for l in locations.values() for i in l["items"]):
                locations[next(iter(by_dir.values()))]["items"].append({"id": item, "qty": 1})
        else:
            template = hook.get("monster")
            fights = [(lid, l["encounter"]) for lid, l in locations.items() if l.get("encounter")]
            if template not in content.MONSTERS:
                template = fights[0][1]["enemies"][0] if fights else "bandit"
            count = sum(e["enemies"].count(template) for _, e in fights)
            if not count:
                # the hook names a foe nobody placed, so put them somewhere
                target = next((lid for lid in by_dir.values() if not locations[lid].get("encounter")),
                              next(iter(by_dir.values())))
                locations[target]["encounter"] = {"enemies": [template], "names": [content.MONSTERS[template]["name"]],
                                                  "text": "Someone is waiting for you."}
                locations[target]["danger"] = 1
                count = 1
            q["goal"] = {"type": "defeat", "template": template, "count": count}
        quests["hook"] = q
        npcs[giver]["quests"].append("hook")

    # leave the lazy Creator some room to grow the map
    for hint in (spec.get("unexplored") or [])[:2]:
        direction = norm(hint.get("direction", ""))
        if direction in OFFSET and direction not in locations["start"]["exits"]:
            locations["start"]["exits"][direction] = {"to": None, "hint": _s(hint.get("hint"), 100, "a way onward")}
    if len(locations["start"]["exits"]) < 4 and not any(isinstance(v, dict) for v in locations["start"]["exits"].values()):
        free = next(d for d in COMPASS if d not in locations["start"]["exits"])
        locations["start"]["exits"][free] = {"to": None, "hint": "a road leading somewhere you haven't been"}

    setting = {"name": _s(spec.get("setting_name"), 60, name), "tone": _s(spec.get("tone"), 120, "grounded"),
               "blurb": _s(spec.get("blurb"), 400)}
    return {"locations": locations, "npcs": npcs, "quests": quests}, setting


def apply(g, premise, spec):
    """Swap a fresh game's world for one built from the premise."""
    world, setting = build_world(spec)
    g["world"] = world
    g["meta"]["location_id"] = "start"
    g["meta"]["setting"] = {"premise": premise, **setting}
    inv = g["player"]["inventory"]
    # the old map is a map of the Ashwood, which doesn't exist here
    g["player"]["inventory"] = [i for i in inv if i["id"] != "old_map"] + [{"id": "lantern", "qty": 1}]
    return g
