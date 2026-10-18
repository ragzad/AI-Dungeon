import copy
import json
import random
import re
import time
from pathlib import Path

from . import content
from .dice import Dice

VERSION = 2
# Top-level keys this game keeps in the ADK session state.
KEYS = ("meta", "mode", "player", "world", "combat", "dialogue", "journal")
MODES = ("exploration", "dialogue", "combat", "dead")


class GameError(Exception):
    """An action the rules don't allow. The message is shown to the player."""


def new_game(name="Wren", seed=None):
    return {
        "meta": {"version": VERSION, "turn": 0, "created": int(time.time()),
                 "rng": {"seed": seed if seed is not None else random.randrange(1 << 30), "count": 0},
                 "location_id": "square", "prev_location_id": None, "log": [], "setting": None},
        "mode": "exploration",
        "player": content.new_player(name),
        "world": content.new_world(),
        "combat": None,
        "dialogue": None,
        "journal": [],
    }


def load(state):
    """Copy the game out of a session state (or any mapping) so it can be changed freely."""
    return {k: copy.deepcopy(state.get(k)) for k in KEYS}


def delta(state, g):
    """The keys of g that differ from what is in state."""
    out = {}
    for k in KEYS:
        if json.dumps(state.get(k), sort_keys=True) != json.dumps(g.get(k), sort_keys=True):
            out[k] = g.get(k)
    return out


def commit(state, g):
    changed = delta(state, g)
    for k, v in changed.items():
        state[k] = v
    return changed


def dice(g):
    rng = g["meta"]["rng"]
    return Dice(rng["seed"], rng["count"])


def store_dice(g, d):
    g["meta"]["rng"]["count"] = d.count


# --- lookups -------------------------------------------------------------

def norm(text):
    return re.sub(r"[^a-z0-9 ]", "", str(text).lower()).strip()


def item_info(item_id, g=None):
    if g is not None:
        info = ((g.get("world") or {}).get("items") or {}).get(item_id)
        if info:
            return info
    info = content.ITEMS.get(item_id)
    if info:
        return info
    name = re.sub(r"^i_", "", str(item_id)).replace("_", " ").title()
    return {"name": name, "kind": "misc", "price": 1, "desc": ""}


def monster_info(template, g=None):
    if g is not None:
        m = ((g.get("world") or {}).get("monsters") or {}).get(template)
        if m:
            return m
    return content.MONSTERS.get(template)


def ability_info(ability_id, g=None):
    if ability_id in content.ABILITIES:
        return content.ABILITIES[ability_id]
    if g is not None:
        return ((g.get("world") or {}).get("abilities") or {}).get(ability_id)
    return None


def learn(g, ability_id):
    """Give the player a generated ability. Returns its name, or None if already known."""
    info = ability_info(ability_id, g)
    if not info or ability_id in g["player"]["abilities"]:
        return None
    g["player"]["abilities"][ability_id] = info["max_uses"]
    journal(g, f"Learned {info['name']}.", "level")
    return info["name"]


def refresh_abilities(g):
    p = g["player"]
    p["abilities"] = {k: (ability_info(k, g) or {"max_uses": v})["max_uses"] for k, v in p["abilities"].items()}
    for k, v in content.ABILITIES.items():
        p["abilities"].setdefault(k, v["max_uses"])


def match(query, options):
    """Find an id in options (id -> name) matching a loose player phrase."""
    q = norm(query)
    if not q:
        return None
    for oid, name in options.items():
        if q == norm(oid) or q == norm(name):
            return oid
    for oid, name in options.items():
        n = norm(name)
        if q in n or n in q or q in norm(oid).replace("_", " "):
            return oid
    words = set(q.split()) - {"the", "a", "an", "to", "of"}
    for oid, name in options.items():
        if words & set(norm(name).split()):
            return oid
    return None


def location(g, loc_id=None):
    return g["world"]["locations"][loc_id or g["meta"]["location_id"]]


def npc(g, npc_id):
    return g["world"]["npcs"][npc_id]


def npcs_here(g):
    loc = location(g)
    return {nid: npc(g, nid)["name"] for nid in loc["npcs"] if npc(g, nid)["alive"]}


def inventory_count(g, item_id):
    return sum(i["qty"] for i in g["player"]["inventory"] if i["id"] == item_id)


def add_item(items, item_id, qty=1):
    for entry in items:
        if entry["id"] == item_id:
            entry["qty"] += qty
            return
    items.append({"id": item_id, "qty": qty})


def remove_item(items, item_id, qty=1):
    for entry in items:
        if entry["id"] == item_id:
            if entry["qty"] < qty:
                raise GameError(f"You don't have enough {item_info(item_id)['name']}.")
            entry["qty"] -= qty
            if entry["qty"] <= 0:
                items.remove(entry)
            return
    raise GameError(f"You don't have a {item_info(item_id)['name']}.")


def inventory_options(g):
    return {i["id"]: item_info(i["id"], g)["name"] for i in g["player"]["inventory"]}


def journal(g, text, kind="note"):
    entries = g["journal"]
    if any(e["text"] == text for e in entries):
        return
    entries.append({"turn": g["meta"]["turn"], "kind": kind, "text": text})
    del entries[:-60]


def log(g, text):
    g["meta"]["log"].append(text)
    del g["meta"]["log"][:-30]


def stat_mod(g, stat):
    return g["player"]["stats"].get(stat, 0)


def _gear(g):
    p = g["player"]
    return [item_info(v, g) for k, v in p["equipped"].items() if v and k != "weapon"]


def _weapon_mod(p, stat):
    st = p["stats"]
    if stat == "dex":  # finesse: whichever is better
        return max(st.get("str", 0), st.get("dex", 0))
    if stat == "wis":  # a focus answers to force of will as much as learning
        return max(st.get("str", 0), st.get("int", 0), st.get("wis", 0), st.get("cha", 0))
    return st.get(stat, 0)


def player_ac(g):
    p = g["player"]
    ac = p["base_ac"] + p["stats"]["dex"]
    for info in _gear(g):
        ac += info.get("ac", 0) + info.get("bonus", {}).get("ac", 0)
    return ac


def attack_bonus(g):
    p = g["player"]
    weapon = item_info(p["equipped"]["weapon"], g) if p["equipped"].get("weapon") else {}
    stat = weapon.get("stat", "str")
    mod = _weapon_mod(p, stat)
    return p["proficiency"] + mod + weapon.get("hit", 0) + sum(i.get("bonus", {}).get("hit", 0) for i in _gear(g))


def weapon_damage(g):
    p = g["player"]
    weapon = item_info(p["equipped"]["weapon"], g) if p["equipped"].get("weapon") else {}
    dmg = weapon.get("damage", "1d4")
    stat = weapon.get("stat", "str")
    mod = _weapon_mod(p, stat)
    return f"{dmg}+{mod}" if mod >= 0 else f"{dmg}{mod}"


def weapon_type(g):
    w = g["player"]["equipped"].get("weapon")
    return item_info(w, g).get("damage_type", "slashing") if w else "bludgeoning"


def player_resist(g):
    out = []
    for info in _gear(g):
        out += info.get("resist", [])
        if info.get("bonus", {}).get("resist"):
            out.append(info["bonus"]["resist"])
    return sorted(set(out))


def bonus_hp(g):
    return sum(i.get("bonus", {}).get("max_hp", 0) for i in _gear(g))


# --- what the UI sees --------------------------------------------------------

def public_view(g):
    """Everything the browser needs, minus things the player hasn't found out."""
    loc_id = g["meta"]["location_id"]
    loc = location(g)
    world = g["world"]
    exits = []
    for direction, dest in loc["exits"].items():
        if isinstance(dest, str):
            exits.append({"direction": direction, "to": dest, "name": world["locations"][dest]["name"]})
        else:
            exits.append({"direction": direction, "to": None, "name": dest.get("hint", "unexplored")})
    p = g["player"]
    player = {
        **{k: p[k] for k in ("name", "class", "level", "xp", "xp_next", "hp", "max_hp", "gold", "stats", "status")},
        "ac": player_ac(g),
        "attack": attack_bonus(g),
        "damage": weapon_damage(g),
        "equipped": {k: (item_info(v, g)["name"] if v else None) for k, v in p["equipped"].items()},
        "equipped_ids": {k: v for k, v in p["equipped"].items() if v},
        "resist": player_resist(g),
        "damage_type": weapon_type(g),
        "inventory": [{"id": i["id"], "qty": i["qty"], **{k: item_info(i["id"], g).get(k) for k in ("name", "kind", "desc", "slot", "tier")},
                       "stats": _item_stats(item_info(i["id"], g)),
                       "combat": _combat_usable(item_info(i["id"], g))}
                      for i in p["inventory"]],
        "abilities": [{"id": k, "name": a["name"], "uses": v, "max_uses": a["max_uses"], "desc": a["desc"],
                       "generated": k not in content.ABILITIES, "target": a.get("target", "enemy")}
                      for k, v in p["abilities"].items() for a in [ability_info(k, g)] if a],
    }
    known = {}
    for lid, l in world["locations"].items():
        if l.get("visited") or lid == loc_id or _adjacent(world, loc_id, lid):
            known[lid] = {"name": l["name"], "x": l["x"], "y": l["y"], "visited": bool(l.get("visited")) or lid == loc_id,
                          "links": [d for d in l["exits"].values() if isinstance(d, str)]}
    dialogue = None
    if g["dialogue"]:
        n = npc(g, g["dialogue"]["npc_id"])
        from .dialogue import price, stock
        nid = g["dialogue"]["npc_id"]
        dialogue = {**g["dialogue"], "name": n["name"], "role": n["role"], "disposition": n["disposition"],
                    "attitude": attitude(n["disposition"]), "memories": len(n["memory"]),
                    "sells": [{"id": i, "name": nm, "price": price(g, nid, i)} for i, nm in stock(n, g).items()],
                    "buys": bool(n["trades"].get("buys"))}
    quests = [{"id": qid, **{k: q[k] for k in ("title", "status", "desc", "progress")}}
              for qid, q in world["quests"].items() if q["status"] != "available"]
    return {
        "mode": g["mode"],
        "turn": g["meta"]["turn"],
        "setting": _setting_view(g),
        "player": player,
        "location": {"id": loc_id, "name": loc["name"], "desc": loc["desc"], "exits": exits,
                     "items": [{"id": i["id"], "name": item_info(i["id"], g)["name"], "qty": i["qty"]} for i in loc["items"]],
                     "npcs": [{"id": nid, "name": npc(g, nid)["name"], "role": npc(g, nid)["role"],
                               "attitude": "hostile" if npc(g, nid)["hostile"] else attitude(npc(g, nid)["disposition"])}
                              for nid in loc["npcs"] if npc(g, nid)["alive"]],
                     "features": list(loc.get("features", {}).keys()), "rest": bool(loc.get("rest"))},
        "map": known,
        "combat": g["combat"],
        "dialogue": dialogue,
        "journal": g["journal"][-30:],
        "quests": quests,
    }


def _item_stats(info):
    if info.get("stats"):
        return info["stats"]
    if info.get("kind") == "weapon":
        return f"{info.get('damage', '1d4')} slashing"
    if info.get("kind") == "armour" and info.get("ac"):
        return f"+{info['ac']} AC"
    return ""


def _combat_usable(info):
    return info.get("kind") == "consumable" and bool(info.get("effect") or info.get("use"))


def _setting_view(g):
    s = g["meta"].get("setting")
    if not s:
        return {"name": "Emberfall", "premise": None}
    return {"name": s["name"], "premise": s["premise"]}


def _adjacent(world, a, b):
    return b in [d for d in world["locations"][a]["exits"].values() if isinstance(d, str)]


def attitude(disposition):
    if disposition >= 75:
        return "friendly"
    if disposition >= 55:
        return "warm"
    if disposition >= 35:
        return "wary"
    if disposition >= 15:
        return "unfriendly"
    return "hostile"


# --- saving --------------------------------------------------------------

SLOT_RE = re.compile(r"^[a-z0-9_-]{1,40}$")


def to_save(g):
    return json.dumps({"version": VERSION, "game": {k: g[k] for k in KEYS}}, indent=1)


def from_save(text):
    data = json.loads(text)
    if data.get("version") != VERSION:
        raise GameError("That save is from a different version of the game.")
    g = data["game"]
    missing = [k for k in KEYS if k not in g]
    if missing:
        raise GameError(f"Save is missing {', '.join(missing)}.")
    if g["mode"] not in MODES:
        raise GameError("Save has an unknown mode.")
    return g


def save_slot(directory, slot, g):
    slot = re.sub(r"[^a-z0-9_-]+", "-", str(slot).lower()).strip("-") or "autosave"
    if not SLOT_RE.match(slot):
        raise GameError("Save names can only use letters, numbers and dashes.")
    path = Path(directory) / f"{slot}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_save(g), encoding="utf-8")
    return slot


def load_slot(directory, slot):
    if not SLOT_RE.match(slot or ""):
        raise GameError("No save with that name.")
    path = Path(directory) / f"{slot}.json"
    if not path.exists():
        raise GameError("No save with that name.")
    return from_save(path.read_text(encoding="utf-8"))


def list_slots(directory):
    out = []
    for path in sorted(Path(directory).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            g = from_save(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({"slot": path.stem, "name": g["player"]["name"], "level": g["player"]["level"],
                    "location": g["world"]["locations"][g["meta"]["location_id"]]["name"],
                    "saved": int(path.stat().st_mtime)})
    return out
