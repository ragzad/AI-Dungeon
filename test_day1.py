from utils import load_game, save_game, get_formatted_state

def main():
    # 1. Load the initial state
    print("--- Loading Game ---")
    state = load_game()
    
    if state:
        print(f"Player: {state['player']['name']}")
        print(f"Current HP: {state['player']['hp']}")
        print(f"Inventory: {state['player']['inventory']}")
        
        # 2. Simulate an event: Player drinks a potion
        print("\n--- Simulating Event: Player finds and drinks a Health Potion ---")
        
        # Logic that the Archivist will eventually handle:
        state['player']['hp'] = 25  # Healed/Buffed
        state['player']['inventory'].append("Empty Potion Bottle") # Update inventory
        
        # 3. Save the new state
        save_game(state)
        
        # 4. Reload to verify persistence
        print("\n--- Verifying Persistence ---")
        new_state = load_game()
        print(f"New HP: {new_state['player']['hp']} (Expected: 25)")
        print(f"New Inventory: {new_state['player']['inventory']}")
        
        if "Empty Potion Bottle" in new_state['player']['inventory']:
             print("\nSUCCESS: Memory persistence is working.")
        else:
             print("\nFAILURE: State did not save correctly.")

if __name__ == "__main__":
    main()