"""Turn-based combat. Every roll happens here; the model only narrates the log."""
from . import content
from .forge import MONSTER_ARCHETYPES
from .state import (GameError, ability_info, add_item, attack_bonus, item_info, journal, location,
                    match, monster_info, player_ac, player_resist, refresh_abilities, remove_item,
                    weapon_damage, weapon_type)

DOT_WORD = {"poisoned": "poison", "burning": "fire", "bleeding": "bleeding"}
ACTIONS = ("attack", "defend", "item", "flee", "power_strike", "second_wind", "ability")
MAX_ENEMIES = 4


def _status(c, name):
    return next((s for s in c["status"] if s["name"] == name), None)


def _add_status(c, name, amount=None):
    existing = _status(c, name)
    turns = content.STATUS[name]["turns"]
    if existing:
        existing["turns"] = max(existing["turns"], turns)
        if amount:
            existing["amount"] = max(existing.get("amount", 0), amount)
    else:
        c["status"].append({"name": name, "turns": turns, **({"amount": amount} if amount else {})})


def _give_status(g, cb, cid, name, amount=None):
    c = cb["combatants"][cid]
    _add_status(c, name, amount)
    if cid == "player":
        g["player"]["status"] = c["status"]


def _ac(c):
    return (c["ac"] + (2 if _status(c, "defending") else 0) - (2 if _status(c, "slowed") else 0)
            + (1 if _status(c, "hasted") else 0))


def _hit_mod(c):
    return (-3 if _status(c, "blinded") else 0) + (2 if _status(c, "hasted") else 0)


def _hurt(g, cb, tid, amount, dtype=None):
    """Apply damage after weaknesses, resistances and wards. Returns (dealt, notes)."""
    t = cb["combatants"][tid]
    notes = []
    if dtype and dtype in t.get("weak", []):
        amount = amount * 3 // 2
        notes.append("weak spot")
    elif dtype and dtype in t.get("resist", []):
        amount = max(1, amount // 2)
        notes.append("resisted")
    ward = _status(t, "shielded")
    if ward and amount > 0:
        soak = min(ward.get("amount", 0), amount)
        ward["amount"] = ward.get("amount", 0) - soak
        amount -= soak
        if soak:
            notes.append(f"ward soaks {soak}")
        if ward["amount"] <= 0:
            t["status"].remove(ward)
    if tid == "player":
        g["player"]["hp"] = max(0, g["player"]["hp"] - amount)
        g["player"]["status"] = t["status"]
        _sync_player(g)
    else:
        t["hp"] = max(0, t["hp"] - amount)
    return amount, notes


def _heal(g, cb, cid, amount):
    c = cb["combatants"][cid]
    if cid == "player":
        p = g["player"]
        healed = min(amount, p["max_hp"] - p["hp"])
        p["hp"] += healed
        _sync_player(g)
        return healed
    healed = min(amount, c["max_hp"] - c["hp"])
    c["hp"] += healed
    return healed


def _event(cb, events, text, kind="info", **extra):
    entry = {"round": cb["round"], "text": text, "kind": kind, **extra}
    cb["log"].append(entry)
    del cb["log"][:-40]
    events.append(entry)


def _alive_enemies(cb):
    return {cid: c for cid, c in cb["combatants"].items() if c["side"] == "enemy" and c["hp"] > 0}


def _sync_player(g):
    cb = g["combat"]
    pc = cb["combatants"]["player"]
    p = g["player"]
    pc.update(hp=p["hp"], max_hp=p["max_hp"], ac=player_ac(g), status=p["status"], name=p["name"])
    resist = player_resist(g)
    if resist:
        pc["resist"] = resist


def _player(g):
    return g["combat"]["combatants"]["player"]


def start_combat(g, enemies, d, intro=None):
    """enemies is a list of {"template": id, "name"?: str, "npc_id"?: str, plus stat overrides}."""
    if g["mode"] == "combat":
        raise GameError("You are already fighting.")
    if g["mode"] == "dead":
        raise GameError("You are dead.")
    if not enemies:
        raise GameError("There is nobody to fight.")
    combatants = {"player": {"name": g["player"]["name"], "side": "player", "dex": g["player"]["stats"]["dex"],
                             "hp": g["player"]["hp"], "max_hp": g["player"]["max_hp"], "ac": player_ac(g),
                             "status": g["player"]["status"]}}
    names = [e.get("name") or monster_info(e["template"], g)["name"] for e in enemies]
    for i, spec in enumerate(enemies):
        name = names[i]
        if names.count(name) > 1:
            name = f"{name} {'ABCDEFGH'[names[:i + 1].count(names[i]) - 1]}"
        combatants[f"e{i + 1}"] = _make_enemy(g, spec, name)
    resist = player_resist(g)
    if resist:
        combatants["player"]["resist"] = resist
    initiative = {}
    for cid, c in combatants.items():
        initiative[cid] = d.d(20) + c["dex"]
    order = sorted(combatants, key=lambda cid: (-initiative[cid], cid != "player", -combatants[cid]["dex"]))
    g["mode"] = "combat"
    g["dialogue"] = None
    g["combat"] = {"id": f"{g['meta']['location_id']}-{g['meta']['turn']}-{d.count}", "round": 1, "order": order, "turn": 0, "initiative": initiative, "combatants": combatants,
                   "log": [], "outcome": None, "rewards": None,
                   "from_location": g["meta"].get("prev_location_id"), "location_id": g["meta"]["location_id"]}
    events = []
    cb = g["combat"]
    if intro:
        _event(cb, events, intro, "info")
    _event(cb, events, "Initiative: " + ", ".join(f"{combatants[c]['name']} {initiative[c]}" for c in order), "initiative")
    # if an enemy won initiative it acts straight away
    if order[0] != "player":
        cb["turn"] = -1
        _advance(g, d, events)
    return {"events": events, "outcome": cb["outcome"]}


def _make_enemy(g, spec, name):
    t = dict(monster_info(spec["template"], g))
    t.update({k: v for k, v in spec.items() if k in ("hp", "ac", "attack", "damage", "name")})
    c = {
        "name": name, "side": "enemy", "template": spec["template"], "npc_id": spec.get("npc_id"),
        "hp": t["hp"], "max_hp": t["hp"], "ac": t["ac"], "attack": t["attack"], "damage": t["damage"],
        "dex": t["dex"], "ai": t["ai"], "xp": t["xp"], "gold": t["gold"], "loot": list(t["loot"]),
        "ability": dict(t["ability"]) if t.get("ability") else None, "status": [], "acted": False,
    }
    if t.get("generated"):
        import copy
        c.update(abilities=copy.deepcopy(t["abilities"]), archetype=t["archetype"], tier=t["tier"],
                 damage_type=t.get("damage_type"), resist=list(t.get("resist", [])), weak=list(t.get("weak", [])),
                 minion=t.get("minion"), desc=t.get("desc", ""))
    return c


def find_ability(g, name):
    """Match a player ability by id or name."""
    if not name:
        return None
    options = {k: (ability_info(k, g) or {}).get("name", k) for k in g["player"]["abilities"]}
    return name if name in options else match(name, options)


def player_action(g, action, d, target=None, item=None, ability=None):
    if g["mode"] != "combat" or not g["combat"] or g["combat"]["outcome"]:
        raise GameError("You aren't in a fight.")
    cb = g["combat"]
    action = (action or "").lower().strip().replace(" ", "_")
    if action == "use_item":
        action = "item"
    if action not in ACTIONS and find_ability(g, action):
        action, ability = "ability", action
    if action == "ability":
        aid = find_ability(g, ability or "")
        if not aid:
            raise GameError(f"You don't know an ability called '{ability}'.")
        if aid in content.ABILITIES:
            action = aid
    if action not in ACTIONS:
        raise GameError(f"Unknown combat action '{action}'. Try attack, defend, item, flee or one of your abilities.")
    if cb["order"][cb["turn"]] != "player":
        raise GameError("It isn't your turn.")
    events = []
    p = g["player"]

    def pick_target():
        enemies = _alive_enemies(cb)
        if target:
            tid = target if target in enemies else match(target, {k: v["name"] for k, v in enemies.items()})
            if not tid:
                raise GameError(f"There's no '{target}' to hit.")
            return tid
        return next(iter(enemies))

    if action in ("attack", "power_strike"):
        if action == "power_strike":
            if p["abilities"].get("power_strike", 0) <= 0:
                raise GameError("You've no strength left for another Power Strike. Rest first.")
            p["abilities"]["power_strike"] -= 1
        tid = pick_target()
        bonus = attack_bonus(g) - (2 if action == "power_strike" else 0)
        dmg_expr = weapon_damage(g)
        w = p["equipped"].get("weapon")
        _attack(g, cb, "player", tid, bonus, dmg_expr, d, events,
                extra="1d6" if action == "power_strike" else None,
                label="Power Strike" if action == "power_strike" else None,
                dtype=weapon_type(g), on_hit=item_info(w, g).get("on_hit") if w else None)
    elif action == "ability":
        info = ability_info(aid, g)
        if p["abilities"].get(aid, 0) <= 0:
            raise GameError(f"You've used up {info['name']} for now. Rest first.")
        p["abilities"][aid] -= 1
        tid = pick_target() if info["target"] == "enemy" else None
        if _use_ability(g, cb, "player", info, tid, d, events) == "escaped":
            return {"events": events, "outcome": cb["outcome"]}
    elif action == "second_wind":
        if p["abilities"].get("second_wind", 0) <= 0:
            raise GameError("You've already used your Second Wind. Rest first.")
        p["abilities"]["second_wind"] -= 1
        roll = d.roll(f"1d10+{p['level']}")
        healed = min(roll["total"], p["max_hp"] - p["hp"])
        p["hp"] += healed
        _event(cb, events, f"{p['name']} catches their breath and recovers {healed} HP.", "heal",
               actor="player", roll=roll)
    elif action == "defend":
        _add_status(_player(g), "defending")
        p["status"] = _player(g)["status"]
        _event(cb, events, f"{p['name']} raises their guard (+2 AC).", "defend", actor="player")
    elif action == "item":
        _use_item_in_combat(g, cb, item, target, d, events, pick_target)
    elif action == "flee":
        if _status(_player(g), "slowed"):
            raise GameError("You're slowed and can't get away. Fight, or wait it out.")
        dc = 10 + 2 * len(_alive_enemies(cb))
        roll = d.d(20)
        total = roll + p["stats"]["dex"]
        if total >= dc:
            _event(cb, events, f"{p['name']} breaks away and flees! (rolled {roll}+{p['stats']['dex']}={total} vs {dc})",
                   "flee", actor="player", roll=roll, dc=dc)
            _finish(g, "fled", events, d)
            return {"events": events, "outcome": cb["outcome"]}
        _event(cb, events, f"{p['name']} tries to flee but can't get clear. (rolled {roll}+{p['stats']['dex']}={total} vs {dc})",
               "flee_fail", actor="player", roll=roll, dc=dc)

    _sync_player(g)
    if not _alive_enemies(cb):
        _finish(g, "victory", events, d)
    else:
        _advance(g, d, events)
    return {"events": events, "outcome": cb["outcome"]}


def _use_item_in_combat(g, cb, item, target, d, events, pick_target):
    p = g["player"]
    if not item:
        raise GameError("Use which item?")
    options = {i["id"]: item_info(i["id"], g)["name"] for i in p["inventory"]}
    iid = item if item in options else match(item, options)
    if not iid:
        raise GameError(f"You don't have '{item}'.")
    info = item_info(iid, g)
    effect = info.get("effect")
    if info["kind"] == "consumable" and info.get("use"):
        remove_item(p["inventory"], iid)
        use = info["use"]
        tid = pick_target() if use["target"] == "enemy" else None
        _use_ability(g, cb, "player", use, tid, d, events, auto_hit=True)
        return
    if info["kind"] != "consumable" or not effect:
        raise GameError(f"The {info['name']} won't help you in a fight.")
    remove_item(p["inventory"], iid)
    if "heal" in effect:
        roll = d.roll(effect["heal"])
        healed = min(roll["total"], p["max_hp"] - p["hp"])
        p["hp"] += healed
        _event(cb, events, f"{p['name']} drinks a {info['name']} and recovers {healed} HP.", "heal", actor="player", roll=roll)
    elif "damage" in effect:
        tid = pick_target()
        t = cb["combatants"][tid]
        roll = d.roll(effect["damage"])
        t["hp"] = max(0, t["hp"] - roll["total"])
        _event(cb, events, f"{p['name']} throws a {info['name']} at {t['name']} for {roll['total']} damage.",
               "damage", actor="player", target=tid, roll=roll, amount=roll["total"])
        if t["hp"] <= 0:
            _event(cb, events, f"{t['name']} falls.", "death", target=tid)
        elif effect.get("status"):
            _add_status(t, effect["status"])
            _event(cb, events, f"{t['name']} is {effect['status']}.", "status", target=tid)
    elif "cure" in effect:
        before = len(p["status"])
        p["status"] = [s for s in p["status"] if s["name"] != effect["cure"]]
        cured = before != len(p["status"])
        _event(cb, events, f"{p['name']} uses an {info['name']}" + (" and the poison fades." if cured else ", to no effect."),
               "heal", actor="player")


def _attack(g, cb, attacker_id, target_id, bonus, dmg_expr, d, events, extra=None, label=None, status=None,
            dtype=None, on_hit=None):
    a = cb["combatants"][attacker_id]
    t = cb["combatants"][target_id]
    if target_id == "player":
        _sync_player(g)
    bonus += _hit_mod(a)
    roll = d.d(20)
    total = roll + bonus
    ac = _ac(t)
    if roll == 1 or (roll != 20 and total < ac):
        _event(cb, events, f"{a['name']} {'uses ' + label + ' on' if label else 'attacks'} {t['name']} and misses. ({roll}+{bonus}={total} vs AC {ac})",
               "miss", actor=attacker_id, target=target_id, roll=roll, total=total, ac=ac)
        return False
    crit = roll == 20
    dmg = d.roll(dmg_expr, crit=crit)
    amount = dmg["total"]
    if extra:
        amount += d.roll(extra, crit=crit)["total"]
    if _status(a, "weakened"):
        amount -= 2
    amount = max(1, amount)
    amount, notes = _hurt(g, cb, target_id, amount, dtype)
    note = f" [{', '.join(notes)}]" if notes else ""
    text = f"{a['name']} {'lands a critical hit on' if crit else ('uses ' + label + ' on' if label else 'hits')} {t['name']} for {amount} damage{note}. ({roll}+{bonus}={total} vs AC {ac})"
    _event(cb, events, text, "crit" if crit else "hit", actor=attacker_id, target=target_id,
           roll=roll, total=total, ac=ac, amount=amount)
    if t["hp"] <= 0:
        _event(cb, events, f"{t['name']} falls." if target_id != "player" else f"{t['name']} collapses.", "death", target=target_id)
        return True
    if status:
        _give_status(g, cb, target_id, status)
        _event(cb, events, f"{t['name']} is {status}.", "status", target=target_id)
    if on_hit and d.d(100) <= on_hit["chance"]:
        _give_status(g, cb, target_id, on_hit["status"])
        _event(cb, events, f"{t['name']} is {on_hit['status']}.", "status", target=target_id)
    return True


def _use_ability(g, cb, aid, ab, target_id, d, events, auto_hit=False):
    """Resolve a generated ability, block by block. Returns "escaped" if the user got away."""
    actor = cb["combatants"][aid]
    if aid == "player":
        _sync_player(g)
    name = ab["name"]
    if ab["target"] == "self":
        bits = []
        for b in ab["blocks"]:
            k = b["kind"]
            if k == "heal":
                roll = d.roll(b["dice"])
                bits.append(f"recovers {_heal(g, cb, aid, roll['total'])} HP")
            elif k == "shield":
                _give_status(g, cb, aid, "shielded", amount=b["amount"])
                bits.append(f"raises a ward that soaks {b['amount']}")
            elif k == "status":
                _give_status(g, cb, aid, b["status"])
                bits.append(f"is {b['status']}")
            elif k == "cure":
                actor["status"] = [s for s in actor["status"] if not content.STATUS[s["name"]].get("bad")]
                if aid == "player":
                    g["player"]["status"] = actor["status"]
                bits.append("shakes off every ailment")
            elif k == "escape":
                _event(cb, events, f"{actor['name']} uses {name} and slips away!", "flee", actor=aid)
                _finish(g, "fled", events, d)
                return "escaped"
            elif k == "summon":
                called = _summon(g, cb, aid, d)
                bits.append(f"calls {called} to the fight" if called else "calls out, but nothing answers")
        _event(cb, events, f"{actor['name']} uses {name}: {', '.join(bits)}.", "special", actor=aid, ability=name)
        return None

    foes = [cid for cid, c in cb["combatants"].items() if c["side"] != actor["side"] and c["hp"] > 0]
    if not foes:
        return None
    targets = foes if ab["target"] == "all_enemies" else [target_id if target_id in foes else foes[0]]
    bonus = (attack_bonus(g) if aid == "player" else actor["attack"]) + _hit_mod(actor)
    primary_hit = False
    for tid in targets:
        t = cb["combatants"][tid]
        if auto_hit:
            roll, total, ac, crit, hit = None, None, None, False, True
        else:
            roll = d.d(20)
            total, ac = roll + bonus, _ac(t)
            crit = roll == 20
            hit = crit or (roll != 1 and total >= ac)
        sums = f" ({roll}+{bonus}={total} vs AC {ac})" if roll is not None else ""
        if not hit:
            _event(cb, events, f"{actor['name']} uses {name} on {t['name']} and misses.{sums}", "miss",
                   actor=aid, target=tid, roll=roll, ability=name)
            continue
        parts, dealt_total = [], 0
        for b in ab["blocks"]:
            if t["hp"] <= 0:
                break
            if b["kind"] == "damage":
                amount = d.roll(b["dice"], crit=crit)["total"] - (2 if _status(actor, "weakened") else 0)
                dealt, notes = _hurt(g, cb, tid, max(1, amount), b["type"])
                dealt_total += dealt
                parts.append(f"{dealt} {b['type']} damage" + (f" [{', '.join(notes)}]" if notes else ""))
            elif b["kind"] == "status":
                _give_status(g, cb, tid, b["status"])
                parts.append(f"{t['name']} is {b['status']}")
            elif b["kind"] == "push":
                t["status"] = [s for s in t["status"] if s["name"] != "defending"]
                _give_status(g, cb, tid, "slowed")
                parts.append(f"{t['name']} is knocked back and slowed")
        lead = "lands a critical" if crit else "uses"
        _event(cb, events, f"{actor['name']} {lead} {name} on {t['name']}: {', '.join(parts)}.{sums}",
               "crit" if crit else "special", actor=aid, target=tid, roll=roll, amount=dealt_total, ability=name)
        if t["hp"] <= 0:
            _event(cb, events, f"{t['name']} falls." if tid != "player" else f"{t['name']} collapses.", "death", target=tid)
        if tid == targets[0]:
            primary_hit = True
    for b in ab["blocks"]:
        if b["kind"] != "chain" or not primary_hit:
            continue
        others = [cid for cid in foes if cid != targets[0] and cb["combatants"][cid]["hp"] > 0][:b["targets"]]
        for tid in others:
            t = cb["combatants"][tid]
            dealt, notes = _hurt(g, cb, tid, d.roll(b["dice"])["total"], b["type"])
            _event(cb, events, f"{name} arcs to {t['name']} for {dealt} {b['type']} damage" +
                   (f" [{', '.join(notes)}]" if notes else "") + ".", "special", actor=aid, target=tid, amount=dealt)
            if t["hp"] <= 0:
                _event(cb, events, f"{t['name']} falls.", "death", target=tid)
    return None


def _summon(g, cb, aid, d):
    actor = cb["combatants"][aid]
    minion = actor.get("minion")
    if not minion or not monster_info(minion, g) or len(_alive_enemies(cb)) >= MAX_ENEMIES:
        return None
    n = len(cb["combatants"])
    cid = f"e{n}"
    while cid in cb["combatants"]:
        n += 1
        cid = f"e{n}"
    c = _make_enemy(g, {"template": minion}, monster_info(minion, g)["name"])
    c["summoned"] = True
    cb["combatants"][cid] = c
    cb["initiative"][cid] = 0
    cb["order"].append(cid)
    return c["name"]


def _start_of_turn(g, cb, cid, d, events):
    """Ticks status effects. Returns False if the combatant loses this turn."""
    c = cb["combatants"][cid]
    if cid == "player":
        _sync_player(g)
    acts = True
    for s in list(c["status"]):
        info = content.STATUS[s["name"]]
        if s["name"] == "stunned":
            acts = False
            _event(cb, events, f"{c['name']} is stunned and loses the turn.", "status", target=cid)
        if info.get("damage") and c["hp"] > 0:
            amount = d.roll(info["damage"])["total"]
            dtype = content.DOT_TYPE.get(s["name"])
            if dtype in c.get("resist", []):
                amount = max(1, amount // 2)
            elif dtype in c.get("weak", []):
                amount = amount * 3 // 2
            c["hp"] = max(0, c["hp"] - amount)
            if cid == "player":
                g["player"]["hp"] = c["hp"]
            _event(cb, events, f"{c['name']} takes {amount} {DOT_WORD.get(s['name'], s['name'])} damage.",
                   "dot", target=cid, amount=amount)
            if c["hp"] <= 0:
                _event(cb, events, f"{c['name']} succumbs.", "death", target=cid)
                acts = False
        if info.get("heal") and c["hp"] > 0:
            healed = _heal(g, cb, cid, d.roll(info["heal"])["total"])
            if healed:
                _event(cb, events, f"{c['name']} regenerates {healed} HP.", "heal", target=cid, amount=healed)
        s["turns"] -= 1
        if s["turns"] <= 0 and s in c["status"]:
            c["status"].remove(s)
    if cid == "player":
        g["player"]["status"] = c["status"]
    return acts


def _advance(g, d, events):
    cb = g["combat"]
    for _ in range(50):
        if cb["outcome"]:
            return
        cb["turn"] += 1
        if cb["turn"] >= len(cb["order"]):
            cb["turn"] = 0
            cb["round"] += 1
        cid = cb["order"][cb["turn"]]
        c = cb["combatants"][cid]
        if c["hp"] <= 0 and cid != "player":
            continue
        acts = _start_of_turn(g, cb, cid, d, events)
        if g["player"]["hp"] <= 0:
            _finish(g, "defeat", events, d)
            return
        if not _alive_enemies(cb):
            _finish(g, "victory", events, d)
            return
        if cid == "player":
            if acts:
                return
            continue
        if acts:
            _enemy_turn(g, cb, cid, d, events)
            if g["player"]["hp"] <= 0:
                _finish(g, "defeat", events, d)
                return
    raise RuntimeError("combat loop did not settle")


def _enemy_turn(g, cb, cid, d, events):
    e = cb["combatants"][cid]
    if e.get("abilities") is not None:
        return _smart_turn(g, cb, cid, d, events)
    ability = e.get("ability")
    use_ability = False
    if ability and ability.get("uses", 0) > 0:
        if e["ai"] == "cunning":
            use_ability = True
        else:
            use_ability = d.d(100) <= 35
    if e["ai"] == "cunning" and e["hp"] <= e["max_hp"] * 0.3 and not e.get("defended"):
        e["defended"] = True
        _add_status(e, "defending")
        _event(cb, events, f"{e['name']} backs off and guards, looking for an opening.", "defend", actor=cid)
        e["acted"] = True
        return
    if use_ability:
        ability["uses"] -= 1
        _attack(g, cb, cid, "player", e["attack"], ability["damage"], d, events,
                label=ability["name"], status=ability.get("status"))
    else:
        _attack(g, cb, cid, "player", e["attack"], e["damage"], d, events)
    e["acted"] = True


def _smart_turn(g, cb, cid, d, events):
    """Enemy AI for generated monsters: each archetype leans on its abilities differently."""
    e = cb["combatants"][cid]
    arch = e.get("archetype", "beast")
    ready = [a for a in e["abilities"] if a["uses"] > 0]
    selfish = [a for a in ready if a["target"] == "self"]
    offence = [a for a in ready if a["target"] != "self"]
    mend = [a for a in selfish if any(b["kind"] in ("heal", "shield", "cure") for b in a["blocks"])]
    summons = [a for a in selfish if any(b["kind"] == "summon" for b in a["blocks"])]
    buffs = [a for a in selfish if a not in mend and a not in summons]
    pick = None
    if e["hp"] <= e["max_hp"] * 0.4 and mend:
        pick = mend[0]
    elif summons and e["hp"] <= e["max_hp"] * 0.6 and len(_alive_enemies(cb)) < MAX_ENEMIES:
        pick = summons[0]
    elif buffs and cb["round"] == 1:
        pick = buffs[0]
    elif offence and d.d(100) <= MONSTER_ARCHETYPES.get(arch, {}).get("chance", 30):
        pick = offence[0]
    if pick:
        pick["uses"] -= 1
        _use_ability(g, cb, cid, pick, "player", d, events)
    elif arch == "skirmisher" and e["hp"] <= e["max_hp"] * 0.3 and not e.get("defended"):
        e["defended"] = True
        _add_status(e, "defending")
        _event(cb, events, f"{e['name']} backs off and guards, looking for an opening.", "defend", actor=cid)
    elif arch == "tank" and not _status(e, "defending") and d.d(100) <= 20:
        _add_status(e, "defending")
        _event(cb, events, f"{e['name']} sets its feet and braces.", "defend", actor=cid)
    else:
        _attack(g, cb, cid, "player", e["attack"], e["damage"], d, events, dtype=e.get("damage_type"))
    e["acted"] = True


LOOT_CHANCE = {"swarm": 10, "boss": 100}


def _finish(g, outcome, events, d=None):
    cb = g["combat"]
    cb["outcome"] = outcome
    p = g["player"]
    p["status"] = []
    if outcome == "defeat":
        g["mode"] = "dead"
        _event(cb, events, f"{p['name']} has fallen. The ash settles over them.", "defeat")
        journal(g, f"Fell in battle at {location(g)['name']}.", "combat")
        return
    g["mode"] = "exploration"
    if outcome == "fled":
        back = cb.get("from_location")
        if back and back in g["world"]["locations"]:
            g["meta"]["location_id"], g["meta"]["prev_location_id"] = back, g["meta"]["location_id"]
        journal(g, "Fled from a fight.", "combat")
        _sync_player(g)
        return
    rewards = {"xp": 0, "gold": 0, "items": []}
    for cid, e in cb["combatants"].items():
        if e["side"] != "enemy":
            continue
        rewards["xp"] += e["xp"]
        rewards["gold"] += d.roll(e["gold"])["total"] if d and not e["gold"].startswith("0d") else 0
        if e.get("tier") and d:
            # generated monsters drop what they carry half the time; hand-made ones always do
            rewards["items"].extend(i for i in e["loot"] if d.d(100) <= 50)
        else:
            rewards["items"].extend(e["loot"])
        tables = g["world"].get("loot") or {}
        if d and e.get("tier") and not e.get("summoned"):
            pool = tables.get(str(e["tier"])) or []
            if pool and d.d(100) <= LOOT_CHANCE.get(e.get("archetype"), 30):
                rewards["items"].append(pool[d.d(len(pool)) - 1])
        if e.get("npc_id"):
            n = g["world"]["npcs"][e["npc_id"]]
            n["alive"] = False
            n["hostile"] = True
            for carried in n.get("carries", []):
                rewards["items"].extend([carried["id"]] * carried["qty"])
            n["carries"] = []
            loc = g["world"]["locations"].get(n["location_id"])
            if loc and e["npc_id"] in loc["npcs"]:
                loc["npcs"].remove(e["npc_id"])
        _quest_kill(g, e)
    p["gold"] += rewards["gold"]
    for iid in rewards["items"]:
        add_item(p["inventory"], iid)
    rewards["names"] = [item_info(i, g)["name"] for i in rewards["items"]]
    cb["rewards"] = rewards
    loot = ", ".join(rewards["names"]) or "nothing"
    _event(cb, events, f"Victory! {rewards['xp']} XP, {rewards['gold']} gold, loot: {loot}.", "victory")
    journal(g, f"Won a fight at {location(g)['name']}. Took {loot}.", "combat")
    loc = location(g)
    loc.pop("encounter", None)
    gain_xp(g, rewards["xp"], events)
    _sync_player(g)


def _quest_kill(g, enemy):
    for q in g["world"]["quests"].values():
        goal = q["goal"]
        if goal["type"] != "defeat" or q["status"] in ("done", "failed"):
            continue
        if goal.get("template") == enemy["template"] or goal.get("npc_id") == enemy.get("npc_id"):
            q["progress"] = min(goal.get("count", 1), q["progress"] + 1)
            if q["progress"] >= goal.get("count", 1) and q["status"] == "active":
                q["status"] = "ready"
                journal(g, f"{q['title']}: done. Go back to {g['world']['npcs'][q['giver']]['name']} for the reward.", "quest")


def gain_xp(g, amount, events=None):
    p = g["player"]
    p["xp"] += amount
    levelled = False
    while p["xp"] >= p["xp_next"]:
        p["level"] += 1
        p["xp_next"] += 150 * p["level"]
        p["max_hp"] += 8
        p["hp"] = min(p["max_hp"], p["hp"] + 8)
        if p["level"] % 2 == 1:
            p["proficiency"] += 1
        refresh_abilities(g)
        levelled = True
        journal(g, f"Reached level {p['level']}.", "level")
        if events is not None and g.get("combat"):
            _event(g["combat"], events, f"{p['name']} reaches level {p['level']}! Max HP is now {p['max_hp']}.", "level")
    return levelled


def summary(g):
    """Short text the Game Master can narrate from."""
    cb = g["combat"]
    if not cb:
        return "No fight."
    parts = []
    for cid in cb["order"]:
        c = cb["combatants"][cid]
        st = ", ".join(s["name"] for s in c["status"])
        if c.get("weak") and c["side"] == "enemy":
            st = ", ".join(x for x in (st, "weak to " + "/".join(c["weak"])) if x)
        parts.append(f"{c['name']} {c['hp']}/{c['max_hp']} HP" + (f" ({st})" if st else "") + (" DOWN" if c["hp"] <= 0 else ""))
    return f"Round {cb['round']}. " + "; ".join(parts) + (f". Outcome: {cb['outcome']}." if cb["outcome"] else ". Your turn.")
