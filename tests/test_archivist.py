import json

import archivist
from conftest import FakeModel
from archivist import get_archivist_response, update_world_state


def test_npc_updates_are_applied(state_file):
    new_state = update_world_state({
        "narrative_cue": "The barkeep is knocked out.",
        "npc_updates": {"barkeep": {"status": "unconscious", "attitude": "hostile"}},
    })
    assert new_state["npcs"]["barkeep"]["status"] == "unconscious"
    assert new_state["npcs"]["barkeep"]["attitude"] == "hostile"
    # and it was saved
    assert json.loads(state_file.read_text())["npcs"]["barkeep"]["attitude"] == "hostile"


def test_unknown_npc_is_ignored(state_file):
    new_state = update_world_state({"npc_updates": {"ghost": {"status": "dead"}}})
    assert "ghost" not in new_state["npcs"]


def test_location_updates_use_current_alias(state_file):
    new_state = update_world_state({
        "location_updates": {"current": {"description": "A smoking ruin.", "remove_exits": ["upstairs"]}},
    })
    tavern = new_state["locations"]["tavern"]
    assert tavern["description"] == "A smoking ruin."
    assert tavern["exits"] == ["street"]


def test_player_update_hp_and_inventory(state_file):
    new_state = update_world_state({"player_update": {"hp": 12, "inventory_add": ["Gold Coin"]}})
    assert new_state["player"]["hp"] == 12
    assert "Gold Coin" in new_state["player"]["inventory"]


def test_archivist_parses_model_json(monkeypatch, start_state):
    reply = {"narrative_cue": "You smash the bottle.", "npc_updates": {"barkeep": {"attitude": "hostile"}}}
    fake = FakeModel(json.dumps(reply))
    monkeypatch.setattr(archivist.genai, "GenerativeModel", fake)

    result = get_archivist_response(start_state, "I smash a bottle over the barkeep's head")
    assert result == reply
    assert "smash a bottle" in fake.prompts[0]


def test_archivist_falls_back_on_bad_json(monkeypatch, start_state):
    monkeypatch.setattr(archivist.genai, "GenerativeModel", FakeModel("not json"))
    result = get_archivist_response(start_state, "I throw my ship")
    assert result == {"narrative_cue": "The action fails to take hold on reality."}
