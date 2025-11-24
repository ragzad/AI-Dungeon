import json
import os

# Define the path to the database
STATE_FILE = "world_state.json"

def load_game():
    """
    Reads the JSON state file and returns it as a Python dictionary.
    If the file doesn't exist, returns None or handles the error.
    """
    if not os.path.exists(STATE_FILE):
        print(f"Error: {STATE_FILE} not found. Please create the file.")
        return None
    
    with open(STATE_FILE, 'r') as f:
        data = json.load(f)
    return data

def save_game(state_data):
    """
    Takes a Python dictionary and overwrites the JSON state file.
    This commits the Archivist's changes to permanent memory.
    """
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=4)
        print(">> World State successfully saved.")
    except Exception as e:
        print(f"Error saving game: {e}")

def get_formatted_state(state_data):
    """
    Helper function to print the state in a readable way for debugging.
    """
    return json.dumps(state_data, indent=2)