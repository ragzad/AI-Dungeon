"""Keeps generated names from sliding into stock fantasy.

The Creator is told to avoid these, but it doesn't always listen, so every opening
is checked: banned names, names used twice in one world, and people's names or
people's names the last few worlds already used. Anything flagged goes back to the
model once for new names, and whatever is still wrong gets a made-up name here."""
import hashlib
import json
import random
import re

# names the model reaches for whatever the premise. Emberfall's own cast isn't on here.
BANNED = {
    "elara", "silas", "oakhaven", "vane", "thorne", "thorn", "lyra", "kael", "kaelen", "aria", "seraphina",
    "eldoria", "ravenwood", "aldric", "eldric", "cedric", "rowan", "gideon", "valerius", "zephyr", "blackwood",
    "shadowfen", "ironhold", "lysandra", "aelar", "whisperwood", "willowbrook", "riverwood", "evelyn", "isolde",
    "alaric", "malakar", "morwen", "grimshaw", "ashford", "varian", "theron", "cassius", "elias", "elowen",
    "finnick", "mira", "kira", "zara", "corvin", "lucian", "draven", "sylas", "nyx", "aurelia", "oberon",
    "eldrin", "faelan", "liora", "vesper", "caelum", "orin", "thalia", "elric", "garrick", "brom", "jareth",
    "sable", "ember", "raven", "crowley", "hollowmere", "stormwind", "duskwood", "mistral",
}

TITLES = {"the", "old", "young", "brother", "sister", "father", "mother", "captain", "lady", "lord", "sir", "dame",
          "master", "mistress", "doctor", "dr", "elder", "auntie", "uncle", "magister", "madam", "mr", "mrs", "ms",
          "saint", "st", "warden", "sergeant", "abbess", "abbot", "prior", "keeper", "big", "little", "cantor",
          "deacon", "sexton", "bishop", "reverend", "friar", "chief", "commander", "lieutenant", "professor",
          "granny", "nan", "widow", "officer", "agent", "inspector", "chaplain", "overseer", "foreman", "doc",
          "boss", "matron", "pilot", "guard"}

# the ones the model leans on most, for the prompt
COMMON = ("Elara", "Silas", "Oakhaven", "Vane", "Thorne", "Lyra", "Kael", "Seraphina", "Eldoria", "Ravenwood",
          "Aldric", "Elias", "Elowen", "Rowan", "Gideon", "Mira", "Isolde", "Alaric", "Cassius", "Vesper", "Corvin",
          "Draven", "Sable", "Orin", "Thalia", "Garrick", "Brom", "Lucian", "Kira", "Blackwood")

ONSET = ["b", "br", "c", "d", "dr", "f", "g", "gr", "h", "k", "l", "m", "n", "p", "r", "s", "sk", "t", "tr", "v",
         "w", "th", "sh", "j", "y", "z"]
VOWEL = ["a", "e", "i", "o", "u", "a", "e", "o", "ai", "ei", "ou", "ea"]
CODA = ["", "", "n", "r", "l", "s", "m", "th", "sk", "nd", "rk", "ll", "st", "x"]


def tokens(name):
    return [t for t in re.split(r"[^a-z]+", str(name).lower()) if t]


def _is_title(word):
    parts = [p for p in re.split(r"[^a-z]+", word.lower()) if p]
    return bool(parts) and parts[-1] in TITLES  # 'Light-Warden' counts as a title


def key_token(name):
    """The part of a person's name that makes it theirs: 'Brother Mallow' -> 'mallow',
    'Light-Warden Sunder-Salt' -> 'sunder-salt'."""
    words = [w.strip(".,'\"").lower() for w in str(name).split()]
    words = [w for w in words if w]
    return next((w for w in words if not _is_title(w)), words[0] if words else "")


def banned(name):
    return any(t in BANNED for t in tokens(name))


def invent(rng, used=()):
    """A short made-up word that isn't banned or already used."""
    used = {u.lower() for u in used}
    for _ in range(200):
        w = "".join(rng.choice(ONSET) + rng.choice(VOWEL) for _ in range(2)) + rng.choice(CODA)
        if 4 <= len(w) <= 9 and w not in BANNED and w not in used:
            return w.capitalize()
    return "Nameless"


def _people(spec):
    return [n.get("name", "") for n in spec.get("npcs") or [] if isinstance(n, dict)]


def named_things(spec):
    """(kind, name) for everything in an opening that has a name."""
    out = [("setting", spec.get("setting_name"))]
    out += [("place", (spec.get("start") or {}).get("name"))]
    out += [("place", p.get("name")) for p in spec.get("places") or [] if isinstance(p, dict)]
    lair = spec.get("boss_lair") or {}
    out += [("place", lair.get("approach_name")), ("place", lair.get("lair_name"))]
    out += [("person", n) for n in _people(spec)]
    out += [("monster", m.get("name")) for m in spec.get("monsters") or [] if isinstance(m, dict)]
    for key in ("items",):
        out += [("item", i.get("name")) for i in spec.get(key) or [] if isinstance(i, dict)]
    for key in ("starting_weapon", "starting_consumable"):
        if isinstance(spec.get(key), dict):
            out.append(("item", spec[key].get("name")))
    return [(k, str(n).strip()) for k, n in out if n and str(n).strip()]


def problems(spec, seen=()):
    """Names to fix, as {name: reason}. seen holds people's names other worlds already used."""
    seen = {s.lower() for s in seen}
    bad, counts = {}, {}
    for kind, name in named_things(spec):
        counts[name.lower()] = counts.get(name.lower(), 0) + 1
        if banned(name):
            bad[name] = "a stock fantasy name"
    for kind, name in named_things(spec):
        if counts[name.lower()] > 1 and name not in bad:
            bad[name] = "used twice in this world"
    for name in _people(spec):
        if name and name not in bad and key_token(name) in seen:
            bad[name] = "already used in another world"
    return bad


def replace_everywhere(spec, old, new):
    """Swap a name for another in every string of the opening, so references stay joined up."""
    pattern = re.compile(r"(?<![A-Za-z])" + re.escape(old) + r"(?![A-Za-z])")

    def walk(v):
        if isinstance(v, str):
            return pattern.sub(new, v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return walk(spec)


def core(name):
    """A name without its leading titles: 'Elder Otho-Vane' -> 'Otho-Vane'."""
    words = str(name).split()
    while len(words) > 1 and _is_title(words[0]):
        words = words[1:]
    return " ".join(words)


def rename(spec, old, new):
    """Swap a full name, then any bare mentions of it without the title."""
    spec = replace_everywhere(spec, old, new)
    if core(old) != old and core(old) and core(new):
        spec = replace_everywhere(spec, core(old), core(new))
    return spec


def apply_renames(spec, renames, bad):
    """Use the model's suggestions where they're good. Returns the new spec and the names still bad."""
    used = {n.lower() for _, n in named_things(spec)}
    left = dict(bad)
    for r in renames or []:
        old, new = str(r.get("old") or "").strip(), str(r.get("new") or "").strip()[:40]
        if old not in left or not new or banned(new) or new.lower() in used:
            continue
        spec = rename(spec, old, new)
        used.add(new.lower())
        left.pop(old)
    return spec, left


def fallback(spec, bad, seed=""):
    """Rename whatever is still wrong with made-up words, keeping titles like 'Brother'."""
    rng = random.Random(hashlib.sha1(f"names|{seed}".encode()).hexdigest())
    used = {t for _, n in named_things(spec) for t in tokens(n)}
    counts = {}
    for name, why in bad.items():
        if why == "used twice in this world":
            # keep the first one, rename the rest
            continue
        words = re.findall(r"[A-Za-z]+|[^A-Za-z]+", name)
        out = []
        for w in words:
            low = w.lower()
            if w.strip() and (low in BANNED or (why != "a stock fantasy name" and low == (tokens(key_token(name)) or [""])[0])):
                fresh = invent(rng, used)
                used.add(fresh.lower())
                out.append(fresh)
            else:
                out.append(w)
        spec = rename(spec, name, "".join(out))
    # duplicates: suffix the later copies on the objects themselves
    for key in ("monsters", "items", "npcs", "places"):
        for obj in spec.get(key) or []:
            if not isinstance(obj, dict) or not obj.get("name"):
                continue
            n = obj["name"].lower()
            counts[n] = counts.get(n, 0) + 1
            if counts[n] > 1 and bad.get(obj["name"]) == "used twice in this world":
                obj["name"] = f"{obj['name']} {invent(rng, used)}"
    return spec


def remember(path, spec, keep=200):
    """Note the people and world names this opening used, so the next world doesn't reuse them."""
    try:
        seen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError, ValueError):
        seen = []
    for name in _people(spec):
        key = key_token(name)
        if key and len(key) > 2 and key not in seen:
            seen.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen[-keep:]), encoding="utf-8")


def recall(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError, ValueError):
        return []


def clean_place(spec, existing=(), seed=""):
    """The same check for a place built mid-game: banned names, or names the world already uses
    for something else, get a made-up replacement. No second model call for these."""
    if not isinstance(spec, dict):
        return spec
    found = [spec.get("name")]
    if isinstance(spec.get("npc"), dict):
        found.append(spec["npc"].get("name"))
    found += [x.get("name") for key in ("new_monsters", "new_items") for x in spec.get(key) or [] if isinstance(x, dict)]
    existing = {str(e).lower() for e in existing}
    bad = {}
    for name in filter(None, (str(n).strip() for n in found)):
        if banned(name):
            bad[name] = "a stock fantasy name"
        elif name.lower() in existing and name != spec.get("name"):
            bad[name] = "already used in this world"
    return fallback(spec, bad, seed) if bad else spec
