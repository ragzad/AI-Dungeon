"""Names: stock fantasy names and repeats get caught and replaced."""
import random

from dungeon import names, premise

from genspec import spec


def test_banned_names_are_spotted_by_word():
    assert names.banned("Elara Thistlewood") and names.banned("Oakhaven")
    assert not names.banned("Brother Mallow") and not names.banned("Saltmarrow")


def test_problems_flags_stock_duplicate_and_seen_names():
    s = spec()
    s["npcs"].append(dict(s["npcs"][0], name="Silas Vane", where="start"))
    s["monsters"].append(dict(s["monsters"][0]))  # a second Silt-Walker
    bad = names.problems(s, seen=["mallow"])
    assert bad["Silas Vane"] == "a stock fantasy name"
    assert bad["Silt-Walker"] == "used twice in this world"
    assert bad["Brother Mallow"] == "already used in another world"


def test_model_renames_are_used_only_when_good():
    s = spec()
    s["npcs"][0]["name"] = "Elara"
    s["quest"]["giver"] = "Elara"
    bad = names.problems(s)
    out, left = names.apply_renames(s, [{"old": "Elara", "new": "Lyra"}], bad)
    assert left == bad  # Lyra is banned too
    out, left = names.apply_renames(s, [{"old": "Elara", "new": "Sister Ebbtide"}], bad)
    assert not left and out["npcs"][0]["name"] == "Sister Ebbtide" and out["quest"]["giver"] == "Sister Ebbtide"


def test_fallback_keeps_titles_and_references():
    s = spec()
    s["npcs"][0]["name"] = "Brother Silas"
    s["quest"]["giver"] = "Brother Silas"
    s["blurb"] += " Brother Silas keeps the keys."
    out = names.fallback(s, names.problems(s), seed="x")
    new = out["npcs"][0]["name"]
    assert new.startswith("Brother ") and "Silas" not in new
    assert out["quest"]["giver"] == new and new in out["blurb"]
    assert not names.problems(out)


def test_invented_words_are_not_banned():
    rng = random.Random(1)
    words = [names.invent(rng) for _ in range(200)]
    assert all(w.lower() not in names.BANNED and 4 <= len(w) <= 9 for w in words)


def test_seen_names_are_remembered(tmp_path):
    path = tmp_path / "seen.json"
    names.remember(path, spec())
    assert names.recall(path) == ["mallow"]
    assert "Brother Mallow" in names.problems(spec(), names.recall(path))


def test_new_places_get_clean_names():
    place = {"name": "Thorne's Rest", "description": "x", "npc": {"name": "Brother Mallow"},
             "new_monsters": [{"name": "Kael Hound"}], "new_items": []}
    out = names.clean_place(place, existing=["Brother Mallow"], seed="s")
    assert "Thorne" not in out["name"] and "Kael" not in out["new_monsters"][0]["name"]
    assert out["npc"]["name"] != "Brother Mallow" and out["npc"]["name"].startswith("Brother ")


def test_build_world_never_keeps_a_banned_name():
    s = spec()
    s["npcs"][0]["name"] = "Elara Vane"
    s["quest"]["giver"] = "Elara Vane"
    w, _, _ = premise.build_world(s, seed="t")
    (npc,) = w["npcs"].values()
    assert not names.banned(npc["name"]) and npc["quests"] == ["hook", "boss"]


def test_renames_reach_bare_mentions_without_the_title():
    s = spec()
    s["npcs"][0]["name"] = "Elder Otho-Vane"
    s["quest"]["giver"] = "Elder Otho-Vane"
    s["quest"]["desc"] = "Otho-Vane needs the nave cleared."
    out, left = names.apply_renames(s, [{"old": "Elder Otho-Vane", "new": "Light-Warden Sunder-Salt"}], names.problems(s))
    assert not left and out["quest"]["desc"] == "Sunder-Salt needs the nave cleared."


def test_titles_are_not_mistaken_for_names():
    assert names.key_token("Light-Warden Sunder-Salt") == "sunder-salt"
    assert names.key_token("Chaplain Hallow-Tide") == "hallow-tide"
    assert names.key_token("Brother Mallow") == "mallow"
    assert names.core("Elder Otho-Vane") == "Otho-Vane"
