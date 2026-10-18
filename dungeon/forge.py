"""Generated gear, monsters and abilities.

The Creator names things, writes the flavour and picks an archetype, a tier
and a few effect blocks. Every number is decided here from a budget, so a
model can't hand out a +40 sword or a rat with 300 HP. Anything that doesn't
fit gets repaired or dropped."""
import re

from . import content

TIERS = (1, 2, 3)
WEAPON_DICE = ["1d4", "1d6", "1d8", "1d10", "1d12", "2d8"]
POWER = ["1d4+1", "1d6+1", "1d8+1", "2d6", "2d6+2", "3d6+1", "3d6+3", "4d6+2"]
HEALS = ["1d4+2", "2d4+2", "2d4+4", "3d4+4", "3d4+6", "4d4+6"]

BAD = tuple(k for k, v in content.STATUS.items() if v.get("bad"))
GOOD = ("regen", "hasted", "defending")
ON_HIT = ("poisoned", "burning", "bleeding", "weakened", "blinded", "slowed")

ITEM_ARCHETYPES = {
    "light_weapon": {"kind": "weapon", "slot": "weapon", "die": 1, "hit": 1, "type": "slashing", "stat": "dex", "price": 8},
    "heavy_weapon": {"kind": "weapon", "slot": "weapon", "die": 3, "hit": 0, "type": "bludgeoning", "stat": "str", "price": 10},
    "ranged": {"kind": "weapon", "slot": "weapon", "die": 1, "hit": 1, "type": "piercing", "stat": "dex", "price": 9},
    "focus": {"kind": "weapon", "slot": "weapon", "die": 2, "hit": 1, "type": "fire", "stat": "wis", "price": 12},
    "light_armour": {"kind": "armour", "slot": "armour", "ac": [1, 2, 2], "price": 10},
    "heavy_armour": {"kind": "armour", "slot": "armour", "ac": [2, 3, 4], "price": 16},
    "shield": {"kind": "armour", "slot": "shield", "ac": [1, 1, 2], "price": 9},
    "potion": {"kind": "consumable", "price": 8},
    "bomb": {"kind": "consumable", "price": 10},
    "tonic": {"kind": "consumable", "price": 8},
    "trinket": {"kind": "trinket", "slot": "trinket", "price": 20},
    "scroll": {"kind": "scroll", "price": 30},
}

# hp/ac/attack scale with tier; archetypes bend them
MONSTER_BASE = {1: {"hp": 12, "ac": 12, "attack": 3, "bonus": 1, "xp": 30},
                2: {"hp": 17, "ac": 12, "attack": 4, "bonus": 2, "xp": 60},
                3: {"hp": 20, "ac": 13, "attack": 4, "bonus": 2, "xp": 100}}
MONSTER_ARCHETYPES = {
    "brute": {"hp": 1.3, "ac": -1, "attack": 0, "die": "1d8", "dex": 0, "type": "bludgeoning", "threat": 1.0,
              "abilities": 1, "chance": 30, "xp": 1.1},
    "skirmisher": {"hp": 0.85, "ac": 1, "attack": 0, "die": "1d6", "dex": 4, "type": "slashing", "threat": 1.0,
                   "abilities": 1, "chance": 45, "xp": 1.0},
    "caster": {"hp": 0.7, "ac": -1, "attack": 1, "die": "1d4", "dex": 2, "type": "fire", "threat": 1.0,
               "abilities": 2, "chance": 75, "xp": 1.1},
    "swarm": {"hp": 0.5, "ac": -1, "attack": 0, "die": "1d4", "dex": 3, "type": "piercing", "threat": 0.5,
              "abilities": 1, "chance": 25, "xp": 0.5},
    "beast": {"hp": 1.0, "ac": 0, "attack": 0, "die": "1d6", "dex": 3, "type": "piercing", "threat": 1.0,
              "abilities": 1, "chance": 35, "xp": 1.0},
    "tank": {"hp": 1.5, "ac": 2, "attack": -1, "die": "1d6", "dex": 0, "type": "bludgeoning", "threat": 1.0,
             "abilities": 1, "chance": 30, "xp": 1.2},
    "boss": {"hp": 2.6, "ac": 1, "attack": 1, "die": "1d8", "dex": 2, "type": "slashing", "threat": 3.0,
             "abilities": 2, "chance": 50, "xp": 3.0},
}
# measured in monsters of the place's own tier; weaker ones cost half per tier below
ENCOUNTER_BUDGET = {1: 2.0, 2: 1.5, 3: 1.5}

BLOCKS = ("damage", "status", "push", "chain", "heal", "shield", "cure", "escape", "summon")
OFFENSIVE_BLOCKS = ("damage", "status", "push", "chain")
SELF_BLOCKS = ("heal", "shield", "status", "cure", "escape", "summon")

# stock signatures for when the Creator gives a monster nothing usable
STOCK = {
    "brute": {"name": "Crushing Blow", "target": "enemy", "blocks": [{"kind": "damage"}, {"kind": "push"}]},
    "skirmisher": {"name": "Dirty Cut", "target": "enemy", "blocks": [{"kind": "damage"}, {"kind": "status", "status": "bleeding"}]},
    "caster": {"name": "Hex", "target": "enemy", "blocks": [{"kind": "damage", "damage_type": "necrotic"}, {"kind": "status", "status": "weakened"}]},
    "swarm": {"name": "Swarm", "target": "enemy", "blocks": [{"kind": "damage"}]},
    "beast": {"name": "Savage Bite", "target": "enemy", "blocks": [{"kind": "damage"}, {"kind": "status", "status": "bleeding"}]},
    "tank": {"name": "Brace", "target": "self", "blocks": [{"kind": "shield"}]},
    "boss": {"name": "Overwhelm", "target": "enemy", "blocks": [{"kind": "damage"}, {"kind": "status", "status": "stunned"}]},
}


def slug(prefix, name, taken=()):
    base = prefix + (re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")[:28] or "x")
    out, n = base, 2
    while out in taken:
        out, n = f"{base}_{n}", n + 1
    return out


def _s(value, limit, default=""):
    return re.sub(r"\s+", " ", str(value or default)).strip()[:limit]


def tier_of(value, cap=3):
    try:
        t = int(value)
    except (TypeError, ValueError):
        t = 1
    return max(1, min(cap, t))


def _dtype(value, default):
    v = str(value or "").lower().strip()
    return v if v in content.DAMAGE_TYPES else default


def _step(table, i):
    return table[max(0, min(len(table) - 1, i))]


# --- abilities ---------------------------------------------------------------

def make_ability(spec, tier, owner="monster", default_type="slashing", taken=(), adjust=0):
    """Build an ability from building blocks. owner is monster, player or item.
    Returns a complete ability with every number filled in."""
    spec = spec or {}
    name = _s(spec.get("name"), 40) or "Strike"
    target = spec.get("target") if spec.get("target") in ("enemy", "all_enemies", "self") else None
    if owner == "monster" and target == "all_enemies":
        target = "enemy"  # there's only ever one of you
    raw = [b for b in (spec.get("blocks") or []) if isinstance(b, dict) and b.get("kind") in BLOCKS][:4]
    if target is None:
        target = "self" if raw and all(b["kind"] in ("heal", "shield", "cure", "escape", "summon") for b in raw) else "enemy"
    allowed = OFFENSIVE_BLOCKS if target != "self" else SELF_BLOCKS
    blocks, kinds = [], set()
    for b in raw:
        k = b["kind"]
        if k not in allowed or k in kinds:
            continue
        if k == "status":
            st = str(b.get("status") or "").lower()
            ok = BAD if target != "self" else GOOD
            if st not in ok or (st == "stunned" and (target == "all_enemies" or owner == "item")):
                continue
            blocks.append({"kind": "status", "status": st})
        elif k == "chain" and (target != "enemy" or owner == "monster"):
            continue
        elif k == "escape" and owner == "monster":
            continue
        elif k == "summon" and owner != "monster":
            continue
        else:
            blocks.append({"kind": k, **({"type": _dtype(b.get("damage_type"), default_type)} if k in ("damage", "chain") else {})})
        kinds.add(k)
        if len(blocks) == 3:
            break
    if not blocks:
        blocks = [{"kind": "heal"}] if target == "self" else [{"kind": "damage", "type": default_type}]
    # chain and push need something to ride on
    if target != "self" and not any(b["kind"] in ("damage", "status") for b in blocks):
        blocks.insert(0, {"kind": "damage", "type": default_type})
        blocks = blocks[:3]

    extra = len(blocks) - 1
    # monsters get one step per tier on top of the first, players two
    base = {"monster": tier + 1, "player": tier * 2 + 1, "item": tier * 2 + 1}[owner] + adjust
    if target == "all_enemies":
        base -= 2
    for b in blocks:
        if b["kind"] == "damage":
            b["dice"] = _step(POWER, base - extra)
        elif b["kind"] == "chain":
            b["dice"] = _step(POWER, base - 2 - extra)
            b["targets"] = 1 if tier < 3 else 2
        elif b["kind"] == "heal":
            b["dice"] = _step(HEALS, tier * 2 - 1 - extra)
        elif b["kind"] == "shield":
            b["amount"] = max(3, 3 + 3 * tier - 2 * extra)
        elif b["kind"] == "summon":
            b["count"] = 1
    strong = target == "all_enemies" or any(
        b["kind"] in ("escape", "summon", "chain") or b.get("status") == "stunned" for b in blocks) or (
        any(b["kind"] == "heal" for b in blocks) and extra)
    uses = (1 if strong else 2) if owner == "player" else 1
    ability = {"id": slug("a_", name, taken), "name": name, "flavour": _s(spec.get("description"), 160),
               "target": target, "blocks": blocks, "uses": uses, "max_uses": uses}
    ability["desc"] = describe_ability(ability)
    return ability


def describe_ability(a):
    who = {"enemy": "one foe", "all_enemies": "every foe", "self": "yourself"}[a["target"]]
    if all(b["kind"] in ("summon", "escape") for b in a["blocks"]):
        who = "once"
    bits = []
    for b in a["blocks"]:
        k = b["kind"]
        if k == "damage":
            bits.append(f"{b['dice']} {b['type']}")
        elif k == "chain":
            bits.append(f"arcs to {b['targets']} more for {b['dice']}")
        elif k == "status":
            bits.append(b["status"])
        elif k == "push":
            bits.append("knocks back (slowed)")
        elif k == "heal":
            bits.append(f"heals {b['dice']}")
        elif k == "shield":
            bits.append(f"ward of {b['amount']}")
        elif k == "cure":
            bits.append("cures ailments")
        elif k == "escape":
            bits.append("escape the fight")
        elif k == "summon":
            bits.append("calls a minion")
    return f"{', '.join(bits)} ({who})"


# --- items -------------------------------------------------------------------

def make_item(spec, tier, taken=(), ability_taken=()):
    """Returns (item_id, item, taught_ability_or_None)."""
    arch = spec.get("archetype") if spec.get("archetype") in ITEM_ARCHETYPES else None
    if not arch:
        return None, None, None
    a = ITEM_ARCHETYPES[arch]
    name = _s(spec.get("name"), 40)
    if not name:
        return None, None, None
    t = tier_of(spec.get("tier"), tier)
    item = {"name": name, "desc": _s(spec.get("description"), 200), "kind": a["kind"], "archetype": arch,
            "tier": t, "price": a["price"] * (1, 3, 7)[t - 1], "generated": True}
    taught = None
    if a["kind"] == "weapon":
        die = a["die"] + t - 1
        status = str(spec.get("on_hit_status") or "").lower()
        if status in ON_HIT:
            die -= 1  # the rider costs a die size
            item["on_hit"] = {"status": status, "chance": (25, 30, 35)[t - 1]}
        item.update(slot="weapon", damage=_step(WEAPON_DICE, die), hit=a["hit"], stat=a["stat"],
                    damage_type=_dtype(spec.get("damage_type"), a["type"]))
        if arch != "focus" and item["damage_type"] not in content.PHYSICAL:
            # elemental steel is allowed, but it costs a die size like a rider does
            item["damage"] = _step(WEAPON_DICE, die - 1)
    elif a["kind"] == "armour":
        item.update(slot=a["slot"], ac=a["ac"][t - 1])
        resist = _dtype(spec.get("resist"), None)
        if resist and resist not in content.PHYSICAL and t >= 2:
            item["resist"] = [resist]
    elif arch == "trinket":
        bonus = str(spec.get("bonus") or "").lower()
        resist = _dtype(spec.get("resist"), None)
        if bonus == "resist" and resist and resist not in content.PHYSICAL:
            item["bonus"] = {"resist": resist}
        elif bonus in ("hit", "ac"):
            item["bonus"] = {bonus: 1}
        else:
            item["bonus"] = {"max_hp": 3 + 2 * t}
        item["slot"] = "trinket"
    elif a["kind"] == "consumable":
        use = spec.get("use") or {}
        if arch == "potion":
            use = {"name": name, "target": "self", "blocks": [{"kind": "heal"}] + [
                b for b in (use.get("blocks") or []) if isinstance(b, dict) and b.get("kind") in ("cure", "status")][:1]}
        elif arch == "bomb":
            blocks = [b for b in (use.get("blocks") or []) if isinstance(b, dict)]
            if not any(b.get("kind") == "damage" for b in blocks):
                blocks.insert(0, {"kind": "damage", "damage_type": spec.get("damage_type") or "fire"})
            use = {"name": name, "target": use.get("target") if use.get("target") in ("enemy", "all_enemies") else "enemy",
                   "blocks": blocks}
            item["combat_only"] = True
        else:  # tonic: a buff or a cure on yourself
            blocks = [b for b in (use.get("blocks") or []) if isinstance(b, dict) and b.get("kind") in ("status", "cure", "shield")]
            use = {"name": name, "target": "self", "blocks": blocks or [{"kind": "cure"}]}
        item["use"] = make_ability(use, t, owner="item", default_type=_dtype(spec.get("damage_type"), "fire"))
    elif arch == "scroll":
        teach = dict(spec.get("use") or {})
        teach.setdefault("name", name)
        taught = make_ability(teach, t, owner="player", default_type=_dtype(spec.get("damage_type"), "radiant"),
                              taken=ability_taken)
        item["teaches"] = taught["id"]
    item["stats"] = describe_item(item)
    return slug("i_", name, taken), item, taught


def describe_item(i):
    kind = i.get("kind")
    if kind == "weapon":
        out = f"{i['damage']} {i.get('damage_type', 'slashing')}" + (f", +{i['hit']} to hit" if i.get("hit") else "")
        if i.get("on_hit"):
            out += f", {i['on_hit']['chance']}% {i['on_hit']['status']} on hit"
        return out
    if kind == "armour":
        return f"+{i['ac']} AC" + (f", resists {i['resist'][0]}" if i.get("resist") else "")
    if kind == "trinket":
        b = i.get("bonus", {})
        return ", ".join(f"resists {v}" if k == "resist" else f"+{v} {k.replace('_', ' ').upper() if k == 'max_hp' else k.upper() if k == 'ac' else 'to hit'}"
                         for k, v in b.items())
    if kind == "consumable" and i.get("use"):
        return i["use"]["desc"]
    if kind == "scroll":
        return "teaches an ability"
    return ""


# --- monsters ----------------------------------------------------------------

def make_monster(spec, tier, taken=(), ability_taken=()):
    """Returns (monster_id, monster) with stats from the budget."""
    name = _s(spec.get("name"), 40)
    arch = spec.get("archetype") if spec.get("archetype") in MONSTER_ARCHETYPES else "beast"
    if not name:
        return None, None
    t = tier_of(spec.get("tier"), tier)
    if arch == "boss":
        t = max(2, t)  # bosses are never a first-room fight
    a, base = MONSTER_ARCHETYPES[arch], MONSTER_BASE[t]
    dtype = _dtype(spec.get("damage_type"), a["type"])
    bonus = base["bonus"] + (-1 if arch == "tank" else 0)
    m = {"name": name, "desc": _s(spec.get("description"), 200), "archetype": arch, "tier": t,
         "hp": max(4, round(base["hp"] * a["hp"])), "ac": base["ac"] + a["ac"], "attack": base["attack"] + a["attack"],
         "damage": f"{a['die']}+{bonus}" if bonus > 0 else a["die"], "dex": a["dex"], "ai": arch,
         "xp": round(base["xp"] * a["xp"]), "threat": a["threat"],
         "gold": "0d1" if arch in ("beast", "swarm") else (f"{t * 3}d6" if arch == "boss" else f"{t}d4"),
         "damage_type": dtype, "loot": [], "generated": True}
    resist = _dtype(spec.get("resist"), None)
    weak = _dtype(spec.get("weak"), None)
    # fair play: one resistance at most, never to plain steel, and only with a weakness to match
    if weak:
        m["weak"] = [weak]
    if resist and weak and resist != weak and resist not in content.PHYSICAL:
        m["resist"] = [resist]
    abilities, ab_taken = [], set(ability_taken)
    for raw in (spec.get("abilities") or [])[:a["abilities"]]:
        ab = make_ability(raw, t, owner="monster", default_type=dtype, taken=ab_taken,
                          adjust=-1 if arch == "swarm" else 0)
        if any(b["kind"] == "summon" for b in ab["blocks"]) and arch not in ("boss", "caster"):
            continue
        ab_taken.add(ab["id"])
        if arch == "boss":
            ab["uses"] = ab["max_uses"] = 2
        abilities.append(ab)
    offensive = any(ab["target"] != "self" for ab in abilities)
    if not abilities or (not offensive and arch != "tank"):
        stock = dict(STOCK[arch])
        stock["blocks"] = [dict(b, damage_type=b.get("damage_type") or dtype) for b in stock["blocks"]]
        ab = make_ability(stock, t, owner="monster", default_type=dtype, taken=ab_taken,
                          adjust=-1 if arch == "swarm" else 0)
        if arch == "boss":
            ab["uses"] = ab["max_uses"] = 2
        abilities.insert(0, ab)
    m["abilities"] = abilities
    m["signature"] = abilities[0]["name"]
    return slug("m_", name, taken), m


def fit_encounter(foes, budget, tier=1):
    """foes is a list of (monster_id, monster). Drop from the end until it fits the budget.
    A boss always fights alone."""
    out, spent = [], 0.0
    for mid, m in foes:
        if m.get("archetype") == "boss":
            if not out and m.get("tier", 1) <= tier:
                return [mid]
            continue
        cost = m.get("threat", 1.0) * 0.5 ** max(0, tier - m.get("tier", 1))
        if spent + cost > budget + 1e-9 or len(out) >= 3:
            continue
        out.append(mid)
        spent += cost
    return out


def loot_tables(items):
    """Per-world loot tables by tier, from the world's own items. Scrolls are rarer."""
    tables = {"1": [], "2": [], "3": []}
    for iid, i in items.items():
        if i.get("kind") in ("weapon", "armour", "consumable", "trinket", "scroll"):
            for t in range(i["tier"], 4):
                tables[str(t)].append(iid)
    return tables


def location_tier(x, y, level):
    # further out is harder, but never ahead of the player's level
    return max(1, min(3, 1 + (abs(x) + abs(y)) // 2, level))


def register(world, items=(), monsters=(), cap=3):
    """Forge and add items and monsters to a world. Returns name->id maps for both."""
    world.setdefault("items", {})
    world.setdefault("monsters", {})
    world.setdefault("abilities", {})
    item_ids, monster_ids = {}, {}
    for spec in list(items)[:10]:
        if not isinstance(spec, dict):
            continue
        iid, item, taught = make_item(spec, cap, taken=world["items"], ability_taken=world["abilities"])
        if not iid:
            continue
        world["items"][iid] = item
        if taught:
            world["abilities"][taught["id"]] = taught
        item_ids[norm(item["name"])] = iid
    for spec in list(monsters)[:6]:
        if not isinstance(spec, dict):
            continue
        mid, m = make_monster(spec, cap, taken=world["monsters"], ability_taken=world["abilities"])
        if not mid:
            continue
        loot = [item_ids.get(norm(n)) or (norm(n).replace(" ", "_") if norm(n).replace(" ", "_") in content.ITEMS else None)
                for n in (spec.get("loot") or [])[:1]]
        m["loot"] = [i for i in loot if i]
        world["monsters"][mid] = m
        monster_ids[norm(m["name"])] = mid
    # summoners need a minion to call
    for mid, m in list(world["monsters"].items()):
        if any(b["kind"] == "summon" for ab in m["abilities"] for b in ab["blocks"]) and not m.get("minion"):
            minion = next((k for k, v in world["monsters"].items() if v["archetype"] == "swarm" and v["tier"] == 1), None)
            if not minion:
                minion, mm = make_monster({"name": f"{m['name']}'s Spawn", "archetype": "swarm", "tier": 1,
                                           "damage_type": m["damage_type"]}, 1, taken=world["monsters"])
                mm["xp"] = 5
                world["monsters"][minion] = mm
            m["minion"] = minion
    world["loot"] = loot_tables(world["items"])
    return item_ids, monster_ids


def norm(text):
    return re.sub(r"[^a-z0-9 ]", "", str(text).lower()).strip()


def resolve_monster(world, ref, names):
    """Find a monster by name (generated) or id (generated or hand-written)."""
    key = norm(ref)
    if key in names:
        return names[key]
    if ref in world.get("monsters", {}):
        return ref
    for mid, m in world.get("monsters", {}).items():
        if norm(m["name"]) == key:
            return mid
    if ref in content.MONSTERS:
        return ref
    return None


def resolve_item(world, ref, names):
    key = norm(ref)
    if key in names:
        return names[key]
    if ref in world.get("items", {}) or ref in content.ITEMS:
        return ref
    for iid, i in world.get("items", {}).items():
        if norm(i["name"]) == key:
            return iid
    return None
