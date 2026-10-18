"""Turns the player's story premise into a starting world.

The Creator writes the opening (places, people, a quest hook) and this checks
it against what the engine can actually run before anything goes in the save."""
import hashlib
import re

from . import content, forge, names
from .state import GameError, item_info, journal, monster_info, norm

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


# --- making sure the opening has what a world needs ---------------------------

MIN_MONSTERS, MAX_MONSTERS = 4, 6
FILLER_NOUN = {"brute": "Bruiser", "skirmisher": "Prowler", "caster": "Whisperer", "swarm": "Swarm",
               "beast": "Hound", "tank": "Sentinel", "boss": "Warden"}
BOSS_LEVEL = 2  # the lair opens at this level


def _monsters(spec):
    return [m for m in spec.get("monsters") or [] if isinstance(m, dict) and _s(m.get("name"), 40)]


def _tier(m):
    try:
        return max(1, min(3, int(m.get("tier") or 1)))
    except (TypeError, ValueError):
        return 1


def monster_needs(spec):
    """How many more monsters of each sort the opening needs: {'tier1': n, 'tier2': n, 'boss': n}."""
    mons = _monsters(spec)
    boss = sum(1 for m in mons if m.get("archetype") == "boss")
    t1 = sum(1 for m in mons if m.get("archetype") != "boss" and _tier(m) == 1)
    t2 = sum(1 for m in mons if m.get("archetype") != "boss" and _tier(m) >= 2)
    need = {"tier1": max(0, 2 - t1), "tier2": max(0, 1 - t2), "boss": 0 if boss else 1}
    short = MIN_MONSTERS - len(mons) - sum(need.values())
    if short > 0:
        need["tier1"] += (short + 1) // 2
        need["tier2"] += short // 2
    return need


def needs(spec, seen=()):
    """Everything worth a second, cheap Creator call: missing monsters and names to change."""
    out = {}
    m = monster_needs(spec)
    if any(m.values()):
        out["monsters"] = m
    bad = names.problems(spec, seen)
    if bad:
        out["rename"] = bad
    return out


def _trim(mons):
    """At most six, keeping a boss, two tier 1s and a tougher one."""
    keep, seen = [], {"boss": 0, "t1": 0, "t2": 0}
    want = {"boss": 1, "t1": 2, "t2": 1}
    group = lambda m: "boss" if m.get("archetype") == "boss" else ("t1" if _tier(m) == 1 else "t2")
    for m in mons:  # required ones first, in order
        g = group(m)
        if seen[g] < want[g]:
            keep.append(m)
            seen[g] += 1
    for m in mons:
        if len(keep) >= MAX_MONSTERS:
            break
        if m not in keep and group(m) != "boss":
            keep.append(m)
    return sorted(keep, key=mons.index)


def merge_fixup(spec, fix, bad=None):
    """Fold the top-up call's monsters and renames into the opening."""
    spec = dict(spec)
    have = {norm(m["name"]) for m in _monsters(spec)}
    extra = [m for m in (fix or {}).get("monsters") or [] if isinstance(m, dict) and _s(m.get("name"), 40)
             and norm(m["name"]) not in have]
    spec["monsters"] = _trim(_monsters(spec) + extra)
    if bad:
        spec, _ = names.apply_renames(spec, (fix or {}).get("renames"), bad)
    return spec


def _word(spec):
    for text in (spec.get("setting_name"), (spec.get("start") or {}).get("name")):
        for w in re.findall(r"[A-Za-z][A-Za-z'-]+", str(text or "")):
            if w.lower() not in names.TITLES and len(w) > 3 and not names.banned(w):
                return w
    return "Hollow"


def repair(spec, seed=""):
    """Last resort, no model involved: fill missing monsters and fix names that are still wrong."""
    spec = dict(spec)
    need = monster_needs(spec)
    word = _word(spec)
    have = _monsters(spec)
    taken = {norm(m["name"]) for m in have}
    filler = []
    plan = ["boss"] * need["boss"] + ["t2"] * need["tier2"] + ["t1"] * need["tier1"]
    archs = ["skirmisher", "brute", "beast", "caster", "tank"]
    for i, kind in enumerate(plan):
        arch = "boss" if kind == "boss" else archs[(i + len(have)) % len(archs)]
        name = (f"The {word} " if kind == "boss" else f"{word} ") + FILLER_NOUN[arch]
        if norm(name) in taken:
            name = f"{name} {('Elder', 'Brood', 'Kin', 'Rank')[i % 4]}"
        taken.add(norm(name))
        filler.append({"name": name, "description": "", "archetype": arch, "tier": 2 if kind != "t1" else 1})
    spec["monsters"] = _trim(have + filler)
    bad = names.problems(spec)
    if bad:
        spec = names.fallback(spec, bad, seed)
    return spec


def _boss_lair(spec, world, locations, by_dir, item_names):
    """Put the world's boss two steps beyond one of the opening places, behind a level gate.
    Returns the lair info for the quest and journal, or None if there's no boss."""
    boss = next((k for k, m in world["monsters"].items() if m["archetype"] == "boss" and not m.get("npc")), None)
    if not boss or not by_dir:
        return None
    m = world["monsters"][boss]
    if m["tier"] > 2:
        # the lair has to be beatable in a normal session, so the world's own boss is tier 2
        rebuilt = next((x for x in _monsters(spec) if norm(x["name"]) == norm(m["name"])), {"name": m["name"]})
        _, m = forge.make_monster({**rebuilt, "archetype": "boss", "tier": 2}, 2, taken=(),
                                  ability_taken=world["abilities"])
        m["loot"] = world["monsters"][boss].get("loot", [])
        if world["monsters"][boss].get("minion"):
            m["minion"] = world["monsters"][boss]["minion"]
        world["monsters"][boss] = m
    lair = spec.get("boss_lair") or {}
    direction = norm(lair.get("direction", ""))
    if direction not in by_dir:
        # the busiest place that isn't somewhere to sleep
        direction = max(by_dir, key=lambda d: (not locations[by_dir[d]].get("rest"),
                                               bool(locations[by_dir[d]].get("encounter"))))
    near_id = by_dir[direction]
    near = locations[near_id]
    dx, dy = OFFSET[direction]
    bname = m["name"]
    approach_name = _s(lair.get("approach_name"), 60) or f"Beyond {near['name']}"
    lair_name = _s(lair.get("lair_name"), 60) or f"Lair of the {bname}"
    if norm(approach_name) == norm(lair_name):
        lair_name = f"{lair_name}, Deep"
    approach_id = _slug("loc_", approach_name, locations)
    approach = {"name": approach_name, "x": 2 * dx, "y": 2 * dy, "tier": 2, "npcs": [], "features": {},
                "desc": _s(lair.get("approach_description"), 600,
                           f"The way narrows past {near['name']}. Signs of the {bname} are everywhere."),
                "exits": {OPPOSITE[direction]: near_id}, "items": [], "danger": 2, "min_level": BOSS_LEVEL,
                "gate_text": _s(lair.get("gate_text"), 160, f"Everything about the way past {near['name']} says turn back for now.")}
    t2 = [k for k, v in world["monsters"].items() if v["tier"] == 2 and v["archetype"] != "boss" and not v.get("npc")]
    t1 = [k for k, v in world["monsters"].items() if v["tier"] == 1 and v["archetype"] not in ("boss",) and not v.get("npc")
          and not v.get("xp", 30) <= 5]
    pool = [(k, world["monsters"][k]) for k in (t2[:1] * 2 + t1[:1])]
    foes = forge.fit_encounter(pool, forge.ENCOUNTER_BUDGET[2], 2) if pool else []
    if foes:
        approach["encounter"] = {"enemies": foes, "names": [world["monsters"][k]["name"] for k in foes],
                                 "text": _s(lair.get("approach_encounter_text"), 200, "Something guards the way.")}
    # one piece of better gear on the way, so a level 2 player can stand up to the boss
    gear = [k for k, v in world["items"].items() if v.get("tier") == 2 and v.get("slot") in ("armour", "shield", "weapon")]
    gear.sort(key=lambda k: ("armour", "shield", "weapon").index(world["items"][k]["slot"]))
    if gear:
        approach["items"].append({"id": gear[0], "qty": 1})
    lair_id = _slug("loc_", lair_name, {**locations, approach_id: approach})
    lair_loc = {"name": lair_name, "x": 3 * dx, "y": 3 * dy, "tier": 2, "npcs": [], "features": {}, "items": [],
                "desc": _s(lair.get("lair_description"), 600, f"This is where the {bname} waits."),
                "exits": {OPPOSITE[direction]: approach_id}, "danger": 3, "boss": True, "min_level": BOSS_LEVEL,
                "gate_text": approach["gate_text"],
                "encounter": {"enemies": [boss], "names": [bname],
                              "text": _s(lair.get("boss_intro"), 200, f"The {bname} rises to meet you.")}}
    approach["exits"][direction] = lair_id
    near["exits"][direction] = approach_id
    locations[approach_id] = approach
    locations[lair_id] = lair_loc
    rumour = _s(lair.get("rumour"), 200, f"People talk about the {bname} in low voices.")
    where = f"It lairs in {lair_name}, past {approach_name}, {direction} of {near['name']}."
    return {"boss": boss, "name": bname, "rumour": rumour, "where": where, "lair": lair_id,
            "title": _s(lair.get("quest_title"), 60) or (f"Face the {bname}" if " " in bname and not bname.lower().startswith("the ")
                                                          else f"Face {bname}")}


def build_world(spec, seed=""):
    """Validate a Creator opening and return (world, setting, kit). Raises GameError if unusable."""
    spec = repair(spec, seed)
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
             "progress": 0, "reward": {"gold": 25, "xp": 100}}
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

    lair = _boss_lair(spec, world, locations, by_dir, item_names)
    if lair:
        hook_q = world["quests"].get("hook")
        if hook_q and norm(hook_q["title"]) == norm(lair["title"]):
            bname = lair["name"]
            lair["title"] = f"Face the {bname}" if " " in bname and not bname.lower().startswith("the ") else f"Face {bname}"
        world["quests"]["boss"] = {
            "title": lair["title"], "giver": giver, "status": "locked" if hook_q else "active",
            "desc": f"{lair['rumour']} {lair['where']} Not before level {BOSS_LEVEL}."[:300],
            "progress": 0, "goal": {"type": "defeat", "template": lair["boss"], "count": 1},
            "reward": {"gold": 60, "xp": 150}, "unlocks_after": "hook" if hook_q else None,
            "ready_at": BOSS_LEVEL, "rumour": lair["rumour"], "where": lair["where"]}
        npcs[giver]["quests"].append("boss")

    # leave the lazy Creator some room to grow the map
    for hint in (spec.get("unexplored") or [])[:2]:
        direction = norm(hint.get("direction", ""))
        if direction in OFFSET and direction not in locations["start"]["exits"]:
            locations["start"]["exits"][direction] = {"to": None, "hint": _s(hint.get("hint"), 100, "a way onward")}
    if len(locations["start"]["exits"]) < 4 and not any(isinstance(v, dict) for v in locations["start"]["exits"].values()):
        free = next(d for d in COMPASS if d not in locations["start"]["exits"])
        locations["start"]["exits"][free] = {"to": None, "hint": "a road leading somewhere you haven't been"}

    # a starting weapon and potion of the world's own. The weapon is tier 1 with a free perk;
    # the potion always heals, whatever the Creator dressed it up as.
    kit = {}
    starter = spec.get("starting_weapon")
    if isinstance(starter, dict):
        arch = starter.get("archetype")
        if arch not in ("light_weapon", "heavy_weapon", "ranged", "focus"):
            arch = "light_weapon"
        sid, sw, _ = forge.make_item({**starter, "archetype": arch, "tier": 1}, 1, taken=world["items"], starter=True)
        if sw:
            world["items"][sid] = sw
            kit["weapon"] = sid
    drink = spec.get("starting_consumable")
    if not isinstance(drink, dict) or not _s(drink.get("name"), 40):
        drink = None
    if drink:
        # a plain heal, as strong as Emberfall's potion; extra effects would water it down
        pid, pot, _ = forge.make_item({**drink, "archetype": "potion", "tier": 1, "use": None}, 1, taken=world["items"])
        if pot:
            pot["starter"] = True
            world["items"][pid] = pot
            kit["potion"] = pid
    if not kit.get("potion"):
        kit["potion"] = next((k for k, v in world["items"].items() if v.get("archetype") == "potion" and v["tier"] == 1), None)
    if not kit.get("potion"):
        word = _word(spec)
        pid, pot, _ = forge.make_item({"name": f"{word} Draught", "archetype": "potion", "tier": 1,
                                       "description": f"A small flask of something the locals swear by."}, 1,
                                      taken=world["items"])
        world["items"][pid] = pot
        kit["potion"] = pid
    world["loot"] = forge.loot_tables({k: v for k, v in world["items"].items() if k != kit.get("weapon")})

    setting = {"name": _s(spec.get("setting_name"), 60, name), "tone": _s(spec.get("tone"), 120, "grounded"),
               "blurb": _s(spec.get("blurb"), 400)}
    return world, setting, kit


def apply(g, premise, spec):
    """Swap a fresh game's world for one built from the premise."""
    world, setting, kit = build_world(spec, seed=hashlib.sha1(premise.encode()).hexdigest()[:12])
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
    boss = world["quests"].get("boss")
    if boss:
        journal(g, f"Rumour: {boss['rumour']}", "lore")
    return g
