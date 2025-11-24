from utils import load_game
from archivist import get_archivist_response, update_world_state

def main():
    print("--- Day 2: Archivist Test ---")
    
    # 1. Load State
    state = load_game()
    print(f"Current State: Player HP {state['player']['hp']}, Inventory: {state['player']['inventory']}")

    # 2. Define an Action
    action = "I want to smash a potion bottle over the Barkeep's head."
    print(f"\nUser Action: '{action}'")
    
    # 3. Call the AI
    print("... Archivist is thinking ...")
    updates = get_archivist_response(state, action)
    
    print("\n--- AI Proposed Updates (JSON) ---")
    print(updates)
    
    # 4. Apply Updates
    new_state = update_world_state(updates)
    
    print("\n--- Resulting World State ---")
    print(f"Barkeep Status: {new_state['npcs']['barkeep']['status']}")
    print(f"Barkeep Attitude: {new_state['npcs']['barkeep']['attitude']}")
    print(f"Player Inventory: {new_state['player']['inventory']}")

if __name__ == "__main__":
    main()