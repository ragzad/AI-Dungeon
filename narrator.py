import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def narrate_scene(current_state, recent_action, world_delta):
    """
    Renders the scene by interpreting the State Delta directly.
    """
    model = genai.GenerativeModel(MODEL_NAME)

    loc_id = current_state.get("current_location_id")
    location = current_state["locations"].get(loc_id, {})
    
    # Items are now guaranteed to be objects by Game Master
    ground_items = [i.get('name', 'Unknown') for i in location.get("items", [])]
    
    # Extract Journal for Context (Memory)
    journal_raw = current_state['player'].get('journal', [])
    # We take the most recent 3 entries to keep the story focused on active threads
    relevant_lore = [f"{e.get('topic')}: {e.get('entry')}" for e in journal_raw[-3:]]

    # Convert Delta to Context strings
    changes_context = []
    p_delta = world_delta.get("player_delta", {})
    q_delta = world_delta.get("quest_update", {})
    l_delta = world_delta.get("location_delta", {})
    
    if p_delta.get("inventory_remove"):
        changes_context.append(f"Player lost/used: {p_delta['inventory_remove']}")
    if p_delta.get("inventory_add"):
        # Handle dicts or strings in delta (Game Master handles the state save, but delta might be raw)
        added = [x['name'] if isinstance(x, dict) else str(x) for x in p_delta['inventory_add']]
        changes_context.append(f"Player gained: {added}")
        
    if l_delta.get("ground_items_add"):
        changes_context.append(f"Appeared on ground: {l_delta['ground_items_add']}")
    if q_delta.get("new_objective"):
        changes_context.append(f"Quest Updated to: {q_delta['new_objective']}")
    
    system_prompt = f"""
    You are the Dungeon Master.
    
    PLAYER ACTION: "{recent_action}"
    
    WHAT ACTUALLY HAPPENED (The Logic Engine):
    - Result: {world_delta.get('action_result')}
    - Changes: {changes_context}
    
    CURRENT CONTEXT:
    - Location: {location.get('name')}
    - Items Nearby: {ground_items}
    - RELEVANT LORE/MEMORY: {relevant_lore}
    
    GUIDELINES:
    1. **Show, Don't Tell:** Use the 'Changes' list to describe the action.
    2. **Immersive:** Keep it punchy and atmospheric.
    3. **CONSISTENCY:** Refer to the 'RELEVANT LORE' if the player mentions specific topics. Do not invent new plots if an existing one explains the situation.
    4. **READING DOCUMENTS:** If the player reads a document, quote it directly in the text.
    """
    
    try:
        response = model.generate_content(system_prompt)
        return response.text
    except Exception:
        return "The world shifts quietly."