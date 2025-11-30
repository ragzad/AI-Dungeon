import json
import os

STATE_FILE = "world_state.json"

def load_game():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, 'r') as f:
        return json.load(f)

def save_game(state_data):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        print(f"Error saving game: {e}")