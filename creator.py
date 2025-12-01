import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location, current_state=None):
    genre = "High Fantasy"
    if current_state:
        genre = current_state.get("story_state", {}).get("genre", "adaptive")

    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    prompt = f"""
    You are the World Forger.
    
    CURRENT GENRE: {genre}
    CONTEXT: Player is at/near {current_location}.
    TARGET: Player interacts with or enters '{target_name}'.
    
    MANDATE: Make it feel ALIVE.
    - Locations CAN (but not limited to) have smells, sounds, and active lighting.
    
    OUTPUT SCHEMA:
    {{
      "type": "location" | "npc" | "item",
      "id": "gen_unique_id",
      "item_name": "Name", 
      "data": {{ 
         "name": "Name",
         "description": "Vivid sensory description.",
         "exits": ["Back to [Previous]"],
         "items": []
      }}
    }}
    """
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception:
        return None

def generate_full_scenario(user_prompt):
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    system_prompt = """
    You are the World Architect. Create a rich, living starting scenario.
    OUTPUT SCHEMA:
    {
      "genre": "String",
      "location": {
         "name": "String",
         "description": "String",
         "exits": ["String"],
         "items": []
      },
      "player": {
         "name": "String",
         "inventory": [{"name": "Item", "description": "Desc", "state": "condition"}]
      },
      "intro_text": "String"
    }
    """
    try:
        response = model.generate_content(f"{system_prompt}\nIDEA: {user_prompt}")
        return json.loads(response.text)
    except Exception:
        return None

def generate_random_scenario_idea():
    model = genai.GenerativeModel(MODEL_NAME)
    return model.generate_content("Generate a text game premise (1 sentence).").text.strip()