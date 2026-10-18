from utils import load_game, save_game


def test_save_and_reload(state_file):
    state = load_game()
    state["player"]["hp"] = 25
    state["player"]["inventory"].append("Empty Potion Bottle")
    save_game(state)

    reloaded = load_game()
    assert reloaded["player"]["hp"] == 25
    assert "Empty Potion Bottle" in reloaded["player"]["inventory"]


def test_load_returns_none_when_no_file(state_file):
    state_file.unlink()
    assert load_game() is None
