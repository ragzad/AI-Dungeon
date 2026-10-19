"""Quest objectives: a short checklist for each quest, built from its goal when the
quest is made and ticked off by the engine as things happen."""
from .state import inventory_count, item_info, journal, monster_info

LIVE = ("active", "ready", "done")


def plural(name):
    words = name.split()
    last = words[-1]
    low = last.lower()
    if low.endswith("wolf"):
        last = last[:-1] + "ves"
    elif low.endswith(("s", "x", "ch", "sh")):
        last += "es"
    elif low.endswith("y") and low[-2:-1] not in "aeiou":
        last = last[:-1] + "ies"
    elif low.endswith("man"):
        last = last[:-3] + "men"
    else:
        last += "s"
    return " ".join(words[:-1] + [last])


def _the(name):
    """'Ash Wolves' -> 'the Ash Wolves', 'The Sunken Prelate' -> 'the Sunken Prelate', mid-sentence."""
    if name.startswith("The "):
        return "the " + name[4:]
    return name if name.lower().startswith(("the ", "a ", "an ")) else f"the {name}"


def _place(name):
    return "the " + name[4:] if name.startswith("The ") else name


def _where(g, template, giver_loc, boss=False):
    """The place a quest's foes wait, if it's somewhere the player has to go."""
    for lid, loc in g["world"]["locations"].items():
        enc = loc.get("encounter") or {}
        if template in (enc.get("enemies") or []) and lid != giver_loc and bool(loc.get("boss")) == boss:
            return lid
    return None


def build(g, q):
    world = g["world"]
    giver = world["npcs"].get(q.get("giver")) or {}
    gname = giver.get("name", "whoever sent you")
    goal = q["goal"]
    obs = []
    contact = world["npcs"].get(q.get("contact") or "")
    if contact:
        obs.append({"id": "talk", "kind": "talk", "npc": q["contact"], "text": f"Speak to {contact['name']}"})
    if q.get("ready_at"):
        obs.append({"id": "level", "kind": "level", "level": q["ready_at"], "text": f"Reach level {q['ready_at']}"})
    if goal["type"] == "defeat":
        m = monster_info(goal.get("template"), g) or {}
        name = goal.get("name") or m.get("name") or "your quarry"
        count = goal.get("count", 1)
        lid = _where(g, goal.get("template"), giver.get("location_id"), boss=bool(q.get("ready_at")))
        if lid:
            obs.append({"id": "reach", "kind": "visit", "loc": lid, "text": f"Find {_place(world['locations'][lid]['name'])}"})
        text = f"Defeat {_the(plural(name))}" if count > 1 else f"Defeat {_the(name)}"
        obs.append({"id": "defeat", "kind": "defeat", "need": count, "text": text})
        obs.append({"id": "return", "kind": "turn_in", "text": f"Return to {gname}"})
    elif goal["type"] == "deliver":
        iname = item_info(goal["item"], g)["name"]
        to = world["npcs"].get(goal.get("to"), giver).get("name", gname)
        obs.append({"id": "find", "kind": "have", "item": goal["item"], "text": f"Find {_the(iname)}"})
        obs.append({"id": "deliver", "kind": "turn_in", "text": f"Bring {_the(iname)} to {to}"})
    for o in obs:
        o["done"] = False
    return obs


def ensure(g):
    for q in g["world"]["quests"].values():
        if "objectives" not in q:
            q["objectives"] = build(g, q)
    return g


def _progress(g, q, o):
    """(have, need) for an objective right now."""
    p, w = g["player"], g["world"]
    kind = o["kind"]
    if kind == "talk":
        return int(bool(w["npcs"].get(o["npc"], {}).get("met"))), 1
    if kind == "level":
        return min(p["level"], o["level"]), o["level"]
    if kind == "visit":
        return int(bool(w["locations"].get(o["loc"], {}).get("visited"))), 1
    if kind == "defeat":
        return min(q.get("progress", 0), o["need"]), o["need"]
    if kind == "have":
        return int(inventory_count(g, o["item"]) > 0 or q["status"] in ("ready", "done")), 1
    if kind == "turn_in":
        return int(q["status"] == "done"), 1
    return 0, 1


def sync(g, quiet=False):
    """Tick off whatever has happened. Returns [(quest title, objective text)] newly done."""
    ensure(g)
    done = []
    for q in g["world"]["quests"].values():
        if q["status"] not in LIVE:
            continue
        for o in q["objectives"]:
            if o["done"]:
                continue
            have, need = _progress(g, q, o)
            if have >= need or q["status"] == "done":
                o["done"] = True
                done.append((q["title"], o["text"]))
                if not quiet:
                    journal(g, f"{q['title']}: {o['text']}. Done.", "quest")
    return done


def view(g, q):
    out = []
    for o in q.get("objectives") or []:
        have, need = _progress(g, q, o)
        if o["done"]:
            have = need
        out.append({"id": o["id"], "text": o["text"], "have": have, "need": need, "done": o["done"],
                    "count": need > 1 and o["kind"] in ("defeat", "level")})
    return out


def current(g):
    """The first unfinished step of the newest live quest, for the pinned line on screen."""
    best = None
    for qid, q in g["world"]["quests"].items():
        if q["status"] not in ("active", "ready"):
            continue
        steps = view(g, q)
        step = next((s for s in steps if not s["done"]), None)
        if not step:
            continue
        started = q.get("started", 0)
        # a reward waiting beats anything else; otherwise the most recently taken quest
        rank = (q["status"] == "ready", started)
        if best is None or rank > best[0]:
            best = (rank, {"quest_id": qid, "quest": q["title"], **step,
                           "step": steps.index(step) + 1, "steps": len(steps)})
    return best[1] if best else None
