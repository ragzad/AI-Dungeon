import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils

START_STATE = {
    "player": {"name": "Traveler", "hp": 20, "max_hp": 20, "inventory": ["Dagger"], "journal": []},
    "current_location_id": "tavern",
    "locations": {
        "tavern": {"name": "The Tavern", "description": "A quiet tavern.", "exits": ["street", "upstairs"]},
    },
    "npcs": {
        "barkeep": {"name": "Barkeep", "location_id": "tavern", "status": "alive", "attitude": "neutral"},
    },
    "story_state": {"genre": "fantasy", "current_objective": "Find a room", "global_tension": 1},
    "world_events": [],
}


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    # point the game at a temp file so the real world_state.json isn't touched
    path = tmp_path / "world_state.json"
    path.write_text(json.dumps(START_STATE))
    monkeypatch.setattr(utils, "STATE_FILE", str(path))
    return path


@pytest.fixture
def start_state():
    return copy.deepcopy(START_STATE)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    """Stands in for genai.GenerativeModel and returns a canned reply."""

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def __call__(self, *args, **kwargs):
        return self

    def generate_content(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return FakeResponse(self.reply)
