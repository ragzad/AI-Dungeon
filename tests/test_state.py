import json

import pytest

from dungeon import state
from dungeon.state import GameError


def test_new_game_has_all_keys(g):
    assert set(g) == set(state.KEYS)
    assert g["mode"] == "exploration"


def test_commit_only_writes_changes(g):
    session_state = dict(g)
    g2 = state.load(session_state)
    g2["player"]["gold"] = 99
    changed = state.commit(session_state, g2)
    assert list(changed) == ["player"]
    assert session_state["player"]["gold"] == 99


def test_load_is_a_copy(g):
    copy = state.load(g)
    copy["player"]["hp"] = 1
    assert g["player"]["hp"] == 30


def test_save_round_trip(tmp_path, g):
    g["player"]["gold"] = 77
    slot = state.save_slot(tmp_path, "My Save!", g)
    assert slot == "my-save"
    assert state.save_slot(tmp_path, "demo-combat", g) == "demo-combat"
    loaded = state.load_slot(tmp_path, slot)
    assert loaded == json.loads(json.dumps(g))
    listing = state.list_slots(tmp_path)
    mine = next(x for x in listing if x["slot"] == "my-save")
    assert mine["location"] == "Emberfall Square" and len(listing) == 2


def test_load_rejects_bad_saves(tmp_path, g):
    (tmp_path / "old.json").write_text(json.dumps({"version": 1, "game": {}}))
    with pytest.raises(GameError):
        state.load_slot(tmp_path, "old")
    with pytest.raises(GameError):
        state.load_slot(tmp_path, "../etc/passwd")
    with pytest.raises(GameError):
        state.load_slot(tmp_path, "missing")


def test_dice_state_survives_save(tmp_path, g):
    d = state.dice(g)
    [d.d(20) for _ in range(5)]
    state.store_dice(g, d)
    expected = d.d(20)
    loaded = state.from_save(state.to_save(g))
    assert state.dice(loaded).d(20) == expected


def test_public_view_hides_secrets(g):
    g["meta"]["location_id"] = "tavern"
    view = state.public_view(g)
    text = json.dumps(view)
    assert "locket from Maren's room" not in text
    assert view["location"]["npcs"][0]["name"] == "the innkeeper"
    assert "Maren" not in json.dumps(view)
    assert view["quests"] == []  # nothing accepted yet


def test_match_is_forgiving():
    opts = {"healing_potion": "Healing Potion", "old_map": "Old Map"}
    assert state.match("potion", opts) == "healing_potion"
    assert state.match("the old map", opts) == "old_map"
    assert state.match("sword", opts) is None
