import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location):
    """
    Generates a new NPC, Item, OR Location.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    prompt = f"""
    You are the World Forger. 
    The player is trying to interact with or go to '{target_name}', but it does not exist in the database.
    
    CONTEXT:
    - Player is currently at: {current_location}
    
    YOUR JOB:
    Determine if '{target_name}' is a Person (NPC), an Item, or a Place (Location).
    
    OUTPUT SCHEMA (Choose one):
    
    OPTION A (NPC):
    {{
      "type": "npc",
      "id": "generated_npc_{target_name.lower().replace(' ', '_')}",
      "data": {{
        "name": "{target_name}",
        "location_id": "{current_location}",
        "status": "alive",
        "attitude": "neutral",
        "hp": 20, "max_hp": 20,
        "description": "Brief visual description."
      }}
    }}
    
    OPTION B (Item):
    {{
      "type": "item",
      "item_name": "{target_name}",
      "description": "Brief description."
    }}
    
    OPTION C (Location):
    {{
      "type": "location",
      "id": "generated_loc_{target_name.lower().replace(' ', '_')}",
      "data": {{
        "name": "{target_name}",
        "description": "Atmospheric description of this new place.",
        "exits": ["back to {current_location}"]
      }}
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Creator Error: {e}")
        return None