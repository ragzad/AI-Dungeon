import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def scan_story_for_entities(story_text, current_state):
    """
    Reads the narrative text and extracts new entities AND LORE.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    # --- INVENTORY HANDLING ---
    raw_inventory = current_state['player'].get('inventory', [])
    existing_items = []
    for item in raw_inventory:
        if isinstance(item, dict):
            existing_items.append(item.get("name", "").lower())
        else:
            existing_items.append(str(item).lower())
    # --------------------------

    existing_npcs = [n['name'].lower() for n in current_state['npcs'].values()]
    existing_locs = [l['name'].lower() for l in current_state['locations'].values()]

    system_prompt = """
    You are The Scribe. You synchronize the Story with the Database.
    
    YOUR JOB:
    Read the provided STORY TEXT. Identify new Items, NPCs, Locations, AND IMPORTANT LORE.
    
    RULES:
    1. **Items/NPCs/Locations:** Only add if PHYSICALLY PRESENT.
    2. **LORE (New!):** If the text reveals specific plot information, secrets, or history (e.g., "The Void Kin hate light", "The code is 0451"), extract it.
    
    OUTPUT SCHEMA:
    {
      "new_items": ["Item Name"],
      "new_npcs": [{"name": "Name", "description": "Context", "presence": "physical"}],
      "new_locations": [{"name": "Name", "description": "Context"}],
      "new_lore": [{"topic": "Topic Name", "entry": "The specific fact learned."}]
    }
    """

    prompt = f"""
    {system_prompt}
    
    EXISTING ENTITIES (Ignore): {existing_items}, {existing_npcs}, {existing_locs}
    
    STORY TEXT TO SCAN:
    "{story_text}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Scribe Error: {e}")
        return {}