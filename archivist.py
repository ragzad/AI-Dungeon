import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def calculate_world_delta(current_state, player_action):
    """
    Calculates purely LOGICAL changes (Physics, Inventory, Quests).
    tuned to be "Generous" and "Fail Forward".
    """
    model = genai.GenerativeModel(MODEL_NAME, generation_config={"response_mime_type": "application/json"})

    loc_id = current_state.get("current_location_id")
    location = current_state["locations"].get(loc_id, {})
    ground_items_raw = location.get("items", [])
    inventory_raw = current_state['player']['inventory']
    journal_raw = current_state['player'].get('journal', [])
    
    # --- SAFETY PATCH: Handle legacy string items in save file ---
    ground_names = []
    for i in ground_items_raw:
        if isinstance(i, dict): ground_names.append(i.get('name'))
        else: ground_names.append(str(i))
        
    inv_names = []
    for i in inventory_raw:
        if isinstance(i, dict): inv_names.append(i.get('name'))
        else: inv_names.append(str(i))
        
    # Format Journal for Context
    journal_context = [f"{entry.get('topic')}: {entry.get('entry')}" for entry in journal_raw[-5:]] # Last 5 entries to keep context fresh but concise
    # -------------------------------------------------------------
    
    system_prompt = f"""
    You are the World Engine (Archivist). Calculate the mathematical/logical changes to the game state.
    
    INPUT CONTEXT:
    - Location: {location.get('name')}
    - Items on Ground: {ground_names}
    - Player Inventory: {inv_names}
    - Player Knowledge (Journal): {journal_context}
    - Current Objective: {current_state['story_state'].get('current_objective')}
    
    YOUR JOB:
    1. Determine the outcome of the PLAYER ACTION.
    2. Maintain CONTINUITY. If the player asks about a topic in their Journal, ensure the result aligns with that known fact.
    
    CRITICAL RULE - BIAS TOWARDS COMPETENCE:
    - The player is a HERO/PROTAGONIST. They are competent.
    - **Simple Actions (Looking, Walking, Talking, Taking):** AUTOMATIC SUCCESS. Do not roll for failure.
    - **Complex Actions (Fighting, Hacking, Persuading):** Use "Fail Forward". If they fail, they should still make progress but at a cost (e.g., they open the door but alert the guards).
    - **NEVER** return a "Dead End" (e.g., "You find nothing", "He ignores you") unless it is physically impossible.
    - If the player looks for something reasonable (e.g. "Contacts in a bar"), **assume it exists** and succeed.
    
    OUTPUT SCHEMA:
    {{
      "action_result": "Success" | "Failure" | "Mixed Success",
      "player_delta": {{
         "hp_change": 0,
         "inventory_add": [], 
         "inventory_remove": ["Item Name"]
      }},
      "location_delta": {{
         "ground_items_add": [], 
         "ground_items_remove": ["Item Name"] 
      }},
      "quest_update": {{
         "new_objective": "String or null",
         "tension_change": 0
      }}
    }}
    """
    
    prompt = f"""
    {system_prompt}
    PLAYER ACTION: "{player_action}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception:
        # Fallback for errors: Default to success logic to keep flow moving
        return { 
            "action_result": "Success", 
            "player_delta": {}, 
            "location_delta": {}, 
            "quest_update": {} 
        }