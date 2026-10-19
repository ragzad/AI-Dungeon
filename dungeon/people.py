"""Who the player knows by name. Strangers go by a description ("the innkeeper",
"a hooded woman") until they introduce themselves or someone names them.

Everything the player or the Game Master sees goes through mask(), so a name
the player hasn't learned never reaches either of them."""
import re

from .names import _is_title
from .state import journal, match, npc

ARTICLES = ("a ", "an ", "the ")


def known(n):
    return n.get("known", True)  # old saves predate this, and everyone in them counts as known


def label(n):
    return n["name"] if known(n) else (n.get("descriptor") or from_role(n.get("role", "")))


def from_role(role):
    """'innkeeper of the Gutter Lantern' -> 'the innkeeper'."""
    r = re.split(r",| of | who | from | at | in ", str(role or "").strip(), maxsplit=1)[0].strip().lower()
    for art in ARTICLES:
        if r.startswith(art):
            r = r[len(art):]
    return f"the {r or 'stranger'}"


def clean_descriptor(text, name, role, taken=()):
    """A descriptor the Creator wrote, checked: short, with an article, and no part of the name in it."""
    d = re.sub(r"\s+", " ", str(text or "")).strip().strip(".")[:48]
    if d and d[0].isupper() and d.split()[0].lower() in ("a", "an", "the"):
        d = d[0].lower() + d[1:]
    lowered = d.lower()
    if not d or any(t.lower() in lowered for t in tokens(name)):
        d = from_role(role)
    elif not lowered.startswith(ARTICLES):
        d = "the " + d
    if d in taken:
        alt = from_role(role)
        d = alt if alt not in taken else "another " + d.split(" ", 1)[-1]
    return d


def tokens(name):
    """Parts of a name that would give it away on their own: 'Maren Holt' -> Maren, Holt."""
    out = []
    for w in str(name).split():
        w = w.strip(".,'\"()")
        if len(w) >= 3 and w[0].isupper() and not _is_title(w):
            out.append(w)
    return out


def _vocab(g):
    """Ordinary words of this world, so a name like 'Mother Ash' doesn't swallow every 'Ash'."""
    world = g["world"]
    text = " ".join([l.get("name", "") + " " + l.get("desc", "") for l in world["locations"].values()]
                    + [i.get("name", "") + " " + i.get("desc", "") for i in (world.get("items") or {}).values()]
                    + [m.get("name", "") for m in (world.get("monsters") or {}).values()])
    return set(re.findall(r"[a-z][a-z'-]+", text.lower()))


def _patterns(g, n, vocab=None):
    vocab = _vocab(g) if vocab is None else vocab
    words = [n["name"]] + [t for t in tokens(n["name"]) if t.lower() not in vocab and t != n["name"]]
    return [re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])") for w in words]


def _strangers(g):
    return [(nid, n) for nid, n in g["world"]["npcs"].items() if not known(n)]


def mask(g, text, strangers=None, vocab=None):
    if not isinstance(text, str) or not text:
        return text
    strangers = _strangers(g) if strangers is None else strangers
    if not strangers:
        return text
    vocab = _vocab(g) if vocab is None else vocab
    for _, n in strangers:
        d = label(n)
        for pat in _patterns(g, n, vocab):
            text = pat.sub(lambda m: _fit(d, m.string, m.start()), text)
    return text


def _fit(desc, text, at):
    before = text[:at].rstrip()
    start = not before or before[-1] in ".!?:\"“" or before.endswith("\n")
    return desc[0].upper() + desc[1:] if start else desc


def mask_deep(g, obj):
    strangers = _strangers(g)
    if not strangers:
        return obj
    vocab = _vocab(g)

    def walk(o):
        if isinstance(o, str):
            return mask(g, o, strangers, vocab)
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o
    return walk(obj)


def reveal(g, nid):
    """The player now knows this person's name. Returns it, or None if they already did."""
    n = npc(g, nid)
    if known(n):
        return None
    before = label(n)
    n["known"] = True
    learned = g["meta"].setdefault("learned", [])
    learned.append({"id": nid, "name": n["name"], "was": before, "turn": g["meta"]["turn"]})
    del learned[:-40]
    journal(g, f"Learned a name: {before} is {n['name']}.", "lore")
    return n["name"]


def reveal_in(g, text, skip=()):
    """Reveal anyone named in something the player heard. Returns the names learned."""
    if not isinstance(text, str) or not text:
        return []
    out = []
    vocab = _vocab(g)
    for nid, n in _strangers(g):
        if nid in skip:
            continue
        if any(p.search(text) for p in _patterns(g, n, vocab)):
            out.append(reveal(g, nid))
    return [x for x in out if x]


def find_here(g, who):
    """An NPC here by name or by how they look."""
    loc = g["world"]["locations"][g["meta"]["location_id"]]
    here = [nid for nid in loc["npcs"] if npc(g, nid)["alive"]]
    if who in here:
        return who
    by_label = {nid: label(npc(g, nid)) for nid in here}
    by_role = {nid: npc(g, nid).get("role", "") for nid in here}
    by_name = {nid: npc(g, nid)["name"] for nid in here}
    return match(who, by_label) or match(who, by_name) or match(who, by_role)


def prepare(g):
    """New game: everyone starts as a stranger, unless their name is on a sign (Brannoc's Forge)."""
    places = " ".join(l["name"] for l in g["world"]["locations"].values())
    taken = set()
    for n in g["world"]["npcs"].values():
        if "known" in n:
            taken.add(label(n))
            continue
        n["descriptor"] = clean_descriptor(n.get("descriptor"), n["name"], n.get("role"), taken)
        taken.add(n["descriptor"])
        n["known"] = any(re.search(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", places) for t in tokens(n["name"]))
    return g


def upgrade(g):
    """Saves from before names had to be learned: everyone is known."""
    for n in g["world"]["npcs"].values():
        n.setdefault("known", True)
    return g


def brief(g):
    """For the Game Master: the people here whose names the player hasn't learned."""
    loc = g["world"]["locations"][g["meta"]["location_id"]]
    return [label(npc(g, nid)) for nid in loc["npcs"] if npc(g, nid)["alive"] and not known(npc(g, nid))]
