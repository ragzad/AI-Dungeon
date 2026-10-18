import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# keep the suite offline: no key means nothing can reach Gemini by accident
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)

from dungeon import state  # noqa: E402


class FakeToolContext:
    def __init__(self, g):
        self.state = dict(g)


@pytest.fixture
def g():
    game = state.new_game("Wren", seed=42)
    return game


@pytest.fixture
def ctx(g):
    return FakeToolContext(g)


def put_in(g, loc_id):
    g["meta"]["prev_location_id"] = g["meta"]["location_id"]
    g["meta"]["location_id"] = loc_id
