import json

import archivist
import director
import narrator
from conftest import FakeModel


def test_full_turn(monkeypatch, state_file, start_state):
    # archivist -> state update -> narrator, with the model calls faked
    cue = "The barkeep accepts the coin and calms down."
    monkeypatch.setattr(archivist.genai, "GenerativeModel", FakeModel(json.dumps({
        "narrative_cue": cue,
        "npc_updates": {"barkeep": {"attitude": "friendly"}},
    })))
    action = "I apologise to the barkeep and offer him a gold coin."
    updates = archivist.get_archivist_response(start_state, action)
    new_state = archivist.update_world_state(updates)

    # every agent shares the same genai module, so swap the fake between steps
    fake_narrator = FakeModel("The barkeep pockets the coin with a grunt.")
    monkeypatch.setattr(narrator.genai, "GenerativeModel", fake_narrator)
    story = narrator.narrate_scene(new_state, action, updates["narrative_cue"])

    assert new_state["npcs"]["barkeep"]["attitude"] == "friendly"
    assert story == "The barkeep pockets the coin with a grunt."
    assert cue in fake_narrator.prompts[0]
    assert "Barkeep (friendly)" in fake_narrator.prompts[0]


def test_narrator_handles_api_error(monkeypatch, start_state):
    monkeypatch.setattr(narrator.genai, "GenerativeModel", FakeModel(RuntimeError("quota")))
    assert narrator.narrate_scene(start_state, "look", "nothing") == "The world is silent."


def test_director_keeps_objective_on_error(monkeypatch, start_state):
    monkeypatch.setattr(director.genai, "GenerativeModel", FakeModel(RuntimeError("quota")))
    result = director.update_story_state(start_state, "look", "nothing")
    assert result["current_objective"] == "Find a room"
