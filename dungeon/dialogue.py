"""Conversation rules. The Dialogue agent writes the words; this decides what they do."""
from . import combat, people
from .state import (GameError, learn, add_item, attitude, inventory_options, item_info, journal, location,
                    match, npc, npcs_here, remove_item)
from .world import end_dialogue

APPROACHES = ("plain", "persuade", "intimidate", "bribe")
BRIBE = 5


def start(g, who, d):
    if g["mode"] == "combat":
        raise GameError("Words won't help now. You're in a fight.")
    if g["mode"] == "dead":
        raise GameError("You are dead.")
    nid = people.find_here(g, who)
    if not nid:
        raise GameError(f"There's nobody called '{who}' here.")
    n = npc(g, nid)
    if n["hostile"]:
        return {"hostile": True, **start_fight(g, nid, d, f"{n['name']} isn't interested in talking.")}
    first = not n["met"]
    n["met"] = True
    g["mode"] = "dialogue"
    g["dialogue"] = {"npc_id": nid, "suggested": [], "last_line": None, "turns": 0, "mood": attitude(n["disposition"])}
    if g["combat"] and g["combat"].get("outcome"):
        g["combat"] = None
    result = {"talking_to": people.label(n), "first_meeting": first, "attitude": attitude(n["disposition"]),
              "quests_turned_in": turn_in(g, nid)}
    return result


def brief(g, nid):
    """What the Dialogue agent gets told about this NPC."""
    n = npc(g, nid)
    quests = {qid: g["world"]["quests"][qid] for qid in n["quests"]}
    return {
        "npc_id": nid, "name": n["name"], "role": n["role"], "personality": n["personality"], "voice": n["voice"],
        "player_knows_your_name": people.known(n),
        "player_calls_you": people.label(n),
        "goals": n["goals"], "disposition": n["disposition"], "attitude": attitude(n["disposition"]),
        "memory_of_player": n["memory"][-8:], "met_before": len(n["memory"]) > 0,
        "secrets_you_could_share": [{"id": s["id"], "text": s["text"], "needs_disposition": s["min_disposition"]}
                                    for s in n["secrets"] if s["id"] not in n.get("shared", [])],
        "quests_you_can_offer": [{"id": qid, "title": q["title"], "desc": q["desc"]}
                                 for qid, q in quests.items() if q["status"] == "available"],
        "sells": [{"id": i, "name": name, "price": price(g, nid, i)} for i, name in stock(n, g).items()],
        "player": {"name": g["player"]["name"], "level": g["player"]["level"], "gold": g["player"]["gold"]},
        "location": location(g)["name"],
        "rumours_you_know": [q["rumour"] + (" " + q["where"] if q["giver"] == nid else "")
                             for q in g["world"]["quests"].values() if q.get("rumour") and q["status"] != "done"],
    }


def social_check(g, nid, approach, d):
    approach = (approach or "plain").lower()
    if approach not in APPROACHES:
        approach = "plain"
    n = npc(g, nid)
    if approach == "plain":
        return None
    if approach == "bribe":
        if g["player"]["gold"] < BRIBE:
            return {"approach": "bribe", "success": False, "note": "not enough gold"}
        g["player"]["gold"] -= BRIBE
        return {"approach": "bribe", "success": True, "gold_paid": BRIBE}
    stat = "cha" if approach == "persuade" else "str"
    dc = max(8, 18 - n["disposition"] // 10) if approach == "persuade" else 14
    roll = d.d(20)
    mod = g["player"]["stats"][stat]
    return {"approach": approach, "roll": roll, "modifier": mod, "total": roll + mod, "dc": dc,
            "success": roll + mod >= dc}


def apply_reply(g, nid, player_line, reply, check, d):
    """Apply what the Dialogue agent decided, within the rules."""
    n = npc(g, nid)
    effects = {}
    change = max(-25, min(15, int(reply.get("disposition_change") or 0)))
    if check:
        if check["approach"] == "bribe" and check["success"]:
            change += 10
        elif check["approach"] == "persuade":
            change += 5 if check["success"] else -3
        elif check["approach"] == "intimidate" and not check["success"]:
            change -= 10
    before = n["disposition"]
    n["disposition"] = max(0, min(100, before + change))
    effects["disposition"] = {"before": before, "after": n["disposition"], "attitude": attitude(n["disposition"])}

    memory = (reply.get("remember") or "").strip() or f"{g['player']['name']} said: {player_line[:80]}"
    n["memory"].append(memory[:160])
    del n["memory"][:-12]

    sid = reply.get("share_secret")
    if sid:
        secret = next((s for s in n["secrets"] if s["id"] == sid), None)
        bar = secret["min_disposition"] - (15 if check and check["success"] else 0) if secret else 999
        if secret and n["disposition"] >= bar:
            n.setdefault("shared", []).append(sid)
            journal(g, f"{n['name']}: {secret['text']}", "lore")
            effects["shared"] = secret["text"]
        else:
            effects["refused_secret"] = True

    qid = reply.get("offer_quest")
    if qid and qid in n["quests"]:
        q = g["world"]["quests"][qid]
        if q["status"] == "available":
            q["status"] = "active"
            q["started"] = g["meta"]["turn"] + 1
            goal = q["goal"]
            if goal["type"] == "defeat" and q["progress"] >= goal.get("count", 1):
                q["status"] = "ready"
            journal(g, f"New quest: {q['title']}. {q['desc']}", "quest")
            effects["quest_started"] = q["title"]
            effects["quests_turned_in"] = turn_in(g, nid)

    hostile = bool(reply.get("turn_hostile")) and (n["disposition"] <= 25 or (check and check["approach"] == "intimidate" and not check["success"]))
    if n["disposition"] <= 5:
        hostile = True
    suggested = [str(s)[:80] for s in (reply.get("suggested_replies") or [])][:3]
    line = str(reply.get("line") or "...")[:600]
    # names are learned by hearing them: their own when they introduce themselves, anyone else's they mention
    learned = [people.reveal(g, nid)] if reply.get("introduced") else []
    learned = [x for x in learned + people.reveal_in(g, line) if x]
    if learned:
        effects["learned_names"] = learned
    g["dialogue"].update(last_line=line, suggested=suggested, mood=str(reply.get("mood") or attitude(n["disposition"]))[:30])
    g["dialogue"]["turns"] += 1
    g["meta"]["turn"] += 1
    if hostile:
        effects["fight"] = start_fight(g, nid, d, f"{n['name']} turns on you!")
    return effects


def start_fight(g, nid, d, intro):
    n = npc(g, nid)
    n["hostile"] = True
    spec = {"template": n["combat"]["template"], "npc_id": nid, **{k: v for k, v in n["combat"].items() if k != "template"}}
    spec["name"] = people.label(n)  # you fight who you see; a stranger stays a stranger
    end_dialogue(g)
    fight = combat.start_combat(g, [spec], d, intro=intro)
    journal(g, f"Fought {n['name']}.", "combat")
    return {"events": fight["events"], "status": combat.summary(g)}


def stock(n, g=None):
    """Shop goods are unlimited; one-off things (quest items) only while the NPC still has them."""
    carries = {c["id"] for c in n.get("carries", [])}
    return {i: item_info(i, g)["name"] for i in n["trades"]["sells"]
            if item_info(i, g)["kind"] != "quest" or i in carries}


def price(g, nid, item_id):
    base = item_info(item_id, g)["price"]
    disp = npc(g, nid)["disposition"]
    factor = 0.8 if disp >= 75 else (1.25 if disp < 35 else 1.0)
    return max(1, round(base * factor))


def trade(g, action, item):
    if g["mode"] != "dialogue":
        raise GameError("You need to be talking to someone to trade.")
    nid = g["dialogue"]["npc_id"]
    n = npc(g, nid)
    p = g["player"]
    action = (action or "").lower()
    if action == "buy":
        carries = {c["id"] for c in n.get("carries", [])}
        goods = stock(n, g)
        iid = item if item in goods else match(item, goods)
        if not iid:
            raise GameError(f"{n['name']} doesn't sell that. They sell: {', '.join(goods.values()) or 'nothing'}.")
        cost = price(g, nid, iid)
        if p["gold"] < cost:
            raise GameError(f"The {item_info(iid, g)['name']} costs {cost} gold and you have {p['gold']}.")
        p["gold"] -= cost
        if iid in carries:
            remove_item(n["carries"], iid)
            n["trades"]["sells"] = [i for i in n["trades"]["sells"] if i != iid]
        add_item(p["inventory"], iid)
        n["disposition"] = min(100, n["disposition"] + 2)
        return {"bought": item_info(iid, g)["name"], "cost": cost, "gold_left": p["gold"]}
    if action == "sell":
        if not n["trades"].get("buys"):
            raise GameError(f"{n['name']} isn't buying.")
        iid = match(item, inventory_options(g))
        if not iid:
            raise GameError(f"You aren't carrying '{item}'.")
        if p["equipped"].get("weapon") == iid and sum(i["qty"] for i in p["inventory"] if i["id"] == iid) == 1:
            raise GameError("You'd be selling the sword out of your hand. Unequip it first.")
        value = max(1, item_info(iid, g)["price"] // 2)
        remove_item(p["inventory"], iid)
        p["gold"] += value
        return {"sold": item_info(iid, g)["name"], "for": value, "gold": p["gold"]}
    raise GameError("Trade action must be buy or sell.")


def give(g, who, item):
    nid = people.find_here(g, who)
    if not nid:
        raise GameError(f"There's nobody called '{who}' here.")
    iid = match(item, inventory_options(g))
    if not iid:
        raise GameError(f"You aren't carrying '{item}'.")
    n = npc(g, nid)
    remove_item(g["player"]["inventory"], iid)
    add_item(n.setdefault("carries", []), iid)
    result = {"gave": item_info(iid, g)["name"], "to": n["name"]}
    for qid, q in g["world"]["quests"].items():
        goal = q["goal"]
        if goal["type"] == "deliver" and goal["item"] == iid and goal["to"] == nid and q["status"] in ("available", "active", "ready"):
            q["status"] = "ready"
    turned = turn_in(g, nid)
    if turned:
        result["quests_turned_in"] = turned
    else:
        n["disposition"] = min(100, n["disposition"] + (5 if item_info(iid, g)["price"] >= 5 else 1))
    return result


def turn_in(g, nid):
    done = []
    for qid, q in g["world"]["quests"].items():
        if q["giver"] != nid or q["status"] != "ready":
            continue
        q["status"] = "done"
        r = q["reward"]
        g["player"]["gold"] += r.get("gold", 0)
        if r.get("disposition"):
            npc(g, nid)["disposition"] = min(100, npc(g, nid)["disposition"] + r["disposition"])
        combat.gain_xp(g, r.get("xp", 0))
        journal(g, f"Completed {q['title']}. Reward: {r.get('gold', 0)} gold, {r.get('xp', 0)} XP.", "quest")
        entry = {"quest": q["title"], **r}
        if r.get("item"):
            add_item(g["player"]["inventory"], r["item"])
            entry["item"] = item_info(r["item"], g)["name"]
        if r.get("ability"):
            entry["learned"] = learn(g, r["ability"])
        unlocked = unlock_after(g, qid)
        if unlocked:
            entry["new_quests"] = unlocked
        done.append(entry)
    return done


def unlock_after(g, qid):
    """Quests that wait for another one, like the boss hunt after the opening job."""
    out = []
    for q in g["world"]["quests"].values():
        if q.get("unlocks_after") != qid or q["status"] != "locked":
            continue
        q["status"] = "active"
        q["started"] = g["meta"]["turn"] + 1
        if q["goal"]["type"] == "defeat" and q["progress"] >= q["goal"].get("count", 1):
            q["status"] = "ready"
        journal(g, f"New quest: {q['title']}. {q['desc']}", "quest")
        out.append(q["title"])
    return out
