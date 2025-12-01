import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def scan_story_for_entities(story_text, current_state):
    """
    Reads the narrative text and extracts new entities that the Narrator invented.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    # Get lists of what we already know to avoid duplicates
    existing_items = [i.lower() for i in current_state['player']['inventory']]
    existing_npcs = [n['name'].lower() for n in current_state['npcs'].values()]
    existing_locs = [l['name'].lower() for l in current_state['locations'].values()]

    system_prompt = """
    You are The Scribe. You synchronize the Story with the Database.
    
    YOUR JOB:
    Read the provided STORY TEXT. Identify any NEW Items, NPCs, or Locations.
    
    RULES:
    1. **Items:** If the text implies the player HAS an item add it.
    2. **NPCs:** If a specific character is named add them.
    3. **Locations:** If a specific landmark is named (e.g. "The Gallows Gambit"), add it.
    4. **NO DUPLICATES:** Do not output entities that already exist in the lists provided.
    5. **NO FLAVOR TEXT:** Do not add "The Sky" or "The Wind". Only tangible, interactive elements.
    
    OUTPUT SCHEMA:
    {
      "new_items": ["Item Name"],
      "new_npcs": [{"name": "Name", "description": "Context from text", "status": "alive"}],
      "new_locations": [{"name": "Name", "description": "Context from text"}]
    }
    """

    prompt = f"""
    {system_prompt}
    
    EXISTING DATA (Ignore these):
    Items: {existing_items}
    NPCs: {existing_npcs}
    Locations: {existing_locs}
    
    STORY TEXT TO SCAN:
    "{story_text}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Scribe Error: {e}")
        return {}