from utils import load_game
from archivist import get_archivist_response, update_world_state
from narrator import narrate_scene

def main():
    print("--- Day 3: Full Loop Test ---")
    
    # 1. Setup - Load the state (which currently has a hostile barkeep from Day 2)
    state = load_game()
    action = "I apologize to the barkeep and offer him a gold coin."
    
    # 2. Archivist (Logic)
    print(f"\n[Action]: {action}")
    print("... Archivist is calculating outcomes ...")
    updates = get_archivist_response(state, action)
    
    # Capture the log for the narrator before we save
    log_msg = updates.get("narrative_cue", "Something happened.")
    
    # 3. Update State
    new_state = update_world_state(updates)
    
    # 4. Narrator (Story)
    print("... Narrator is writing ...")
    story = narrate_scene(new_state, action, log_msg)
    
    print("\n" + "="*40)
    print("THE STORY:")
    print(story)
    print("="*40)

if __name__ == "__main__":
    main()