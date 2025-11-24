import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location):
    """
    Generates a new NPC or Item that fits the current world context.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    prompt = f"""
    You are the World Forger. The player is trying to interact with '{target_name}', but it does not exist in the database.
    
    YOUR JOB:
    Create a JSON object for this new entity. 
    - Context: The player is currently at '{current_location}'.
    - If it sounds like a character, create an NPC.
    - If it sounds like an object, create an Item.
    
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
        "hp": 20,
        "max_hp": 20,
        "description": "A generated description of the entity."
      }}
    }}
    
    OPTION B (Item):
    {{
      "type": "item",
      "item_name": "{target_name}",
      "description": "A generated description of the item."
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Creator Error: {e}")
        return None