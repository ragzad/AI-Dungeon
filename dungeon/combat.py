"""Turn-based combat. Every roll happens here; the model only narrates the log."""
from . import content
from .state import (GameError, add_item, attack_bonus, item_info, journal, location,
                    match, player_ac, remove_item, weapon_damage)

DOT_WORD = {"poisoned": "poison", "burning": "fire", "bleeding": "bleeding"}
ACTIONS = ("attack", "defend", "item", "flee", "power_strike", "second_wind")


def _status(c, name):
    return next((s for s in c["status"] if s["name"] == name), None)


def _add_status(c, name):
    existing = _status(c, name)
    turns = content.STATUS[name]["turns"]
    if existing:
        existing["turns"] = max(existing["turns"], turns)
    else:
        c["status"].append({"name": name, "turns": turns})


def _ac(c):
    return c["ac"] + (2 if _status(c, "defending") else 0)


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
    names = [e.get("name") or content.MONSTERS[e["template"]]["name"] for e in enemies]
    for i, spec in enumerate(enemies):
        t = dict(content.MONSTERS[spec["template"]])
        t.update({k: v for k, v in spec.items() if k in ("hp", "ac", "attack", "damage", "name")})
        name = names[i]
        if names.count(name) > 1:
            name = f"{name} {'ABCDEFGH'[names[:i + 1].count(names[i]) - 1]}"
        combatants[f"e{i + 1}"] = {
            "name": name, "side": "enemy", "template": spec["template"], "npc_id": spec.get("npc_id"),
            "hp": t["hp"], "max_hp": t["hp"], "ac": t["ac"], "attack": t["attack"], "damage": t["damage"],
            "dex": t["dex"], "ai": t["ai"], "xp": t["xp"], "gold": t["gold"], "loot": list(t["loot"]),
            "ability": dict(t["ability"]) if t.get("ability") else None, "status": [], "acted": False,
        }
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


def player_action(g, action, d, target=None, item=None):
    if g["mode"] != "combat" or not g["combat"] or g["combat"]["outcome"]:
        raise GameError("You aren't in a fight.")
    cb = g["combat"]
    action = (action or "").lower().strip().replace(" ", "_")
    if action == "use_item":
        action = "item"
    if action not in ACTIONS:
        raise GameError(f"Unknown combat action '{action}'. Try attack, defend, item, flee, power_strike or second_wind.")
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
        _attack(g, cb, "player", tid, bonus, dmg_expr, d, events,
                extra="1d6" if action == "power_strike" else None,
                label="Power Strike" if action == "power_strike" else None)
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
    options = {i["id"]: item_info(i["id"])["name"] for i in p["inventory"]}
    iid = item if item in options else match(item, options)
    if not iid:
        raise GameError(f"You don't have '{item}'.")
    info = item_info(iid)
    effect = info.get("effect")
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


def _attack(g, cb, attacker_id, target_id, bonus, dmg_expr, d, events, extra=None, label=None, status=None):
    a = cb["combatants"][attacker_id]
    t = cb["combatants"][target_id]
    if target_id == "player":
        _sync_player(g)
    roll = d.d(20)
    total = roll + bonus
    ac = _ac(t)
    verb = label or "attacks"
    if roll == 1 or (roll != 20 and total < ac):
        _event(cb, events, f"{a['name']} {'uses ' + label + ' on' if label else 'attacks'} {t['name']} and misses. ({roll}+{bonus}={total} vs AC {ac})",
               "miss", actor=attacker_id, target=target_id, roll=roll, total=total, ac=ac)
        return False
    crit = roll == 20
    dmg = d.roll(dmg_expr, crit=crit)
    amount = dmg["total"]
    if extra:
        amount += d.roll(extra, crit=crit)["total"]
    amount = max(1, amount)
    if target_id == "player":
        g["player"]["hp"] = max(0, g["player"]["hp"] - amount)
        _sync_player(g)
    else:
        t["hp"] = max(0, t["hp"] - amount)
    text = f"{a['name']} {'lands a critical hit on' if crit else ('uses ' + label + ' on' if label else 'hits')} {t['name']} for {amount} damage. ({roll}+{bonus}={total} vs AC {ac})"
    _event(cb, events, text, "crit" if crit else "hit", actor=attacker_id, target=target_id,
           roll=roll, total=total, ac=ac, amount=amount)
    if t["hp"] <= 0:
        _event(cb, events, f"{t['name']} falls." if target_id != "player" else f"{t['name']} collapses.", "death", target=target_id)
    elif status:
        _add_status(t, status)
        if target_id == "player":
            g["player"]["status"] = t["status"]
        _event(cb, events, f"{t['name']} is {status}.", "status", target=target_id)
    return True


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
            c["hp"] = max(0, c["hp"] - amount)
            if cid == "player":
                g["player"]["hp"] = c["hp"]
            _event(cb, events, f"{c['name']} takes {amount} {DOT_WORD.get(s['name'], s['name'])} damage.",
                   "dot", target=cid, amount=amount)
            if c["hp"] <= 0:
                _event(cb, events, f"{c['name']} succumbs.", "death", target=cid)
                acts = False
        s["turns"] -= 1
        if s["turns"] <= 0:
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
        rewards["items"].extend(e["loot"])
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
    cb["rewards"] = rewards
    loot = ", ".join(item_info(i)["name"] for i in rewards["items"]) or "nothing"
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
        p["abilities"] = {k: v["max_uses"] for k, v in content.ABILITIES.items()}
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
        parts.append(f"{c['name']} {c['hp']}/{c['max_hp']} HP" + (f" ({st})" if st else "") + (" DOWN" if c["hp"] <= 0 else ""))
    return f"Round {cb['round']}. " + "; ".join(parts) + (f". Outcome: {cb['outcome']}." if cb["outcome"] else ". Your turn.")
