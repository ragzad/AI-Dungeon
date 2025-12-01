import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location, current_state=None):
    """
    Generates a new specific entity (Location, NPC, or Item) during gameplay.
    """
    genre = "High Fantasy"
    if current_state:
        genre = current_state.get("story_state", {}).get("genre", "adaptive")

    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    prompt = f"""
    You are the World Forger.
    
    CURRENT GENRE: {genre}
    CONTEXT: Player is at {current_location}.
    TARGET: Player wants to go to/interact with '{target_name}'.
    
    RULES:
    1. **MATCH THE GENRE:** Ensure the creation fits the current setting.
    2. **SPATIAL LOGIC:** Ensure locations make physical sense.
    3. **VISUAL EXITS:** For locations, 'suggested_exits' must be visual descriptions, not names.
    
    OUTPUT SCHEMA:
    {{
      "type": "location" | "npc" | "item",
      "id": "gen_...",
      "item_name": "...", 
      "data": {{ ... }}
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Creator Error: {e}")
        return None

def generate_full_scenario(user_prompt):
    """
    Generates a complete starting state based on a user concept.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    system_prompt = """
    You are the World Architect. 
    Your job is to initialize a text-adventure game state based on a theme.
    
    INPUT: A theme or scenario idea.
    
    OUTPUT: A JSON object containing:
    1. genre: The specific sub-genre.
    2. location: The starting room details.
    3. player: A suitable character name and starting inventory (3-5 items).
       - Inventory items MUST be objects with {name, description, state}.
    4. intro_text: A gripping opening paragraph setting the scene.
    
    OUTPUT SCHEMA:
    {
      "genre": "String",
      "location": {
         "name": "String",
         "description": "String",
         "exits": ["String"],
         "suggested_exits": ["String"]
      },
      "player": {
         "name": "String",
         "inventory": [
            {"name": "Item Name", "description": "Desc", "state": "condition"}
         ]
      },
      "intro_text": "String"
    }
    """
    
    prompt = f"""
    {system_prompt}
    USER SCENARIO IDEA: "{user_prompt}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Genesis Error: {e}")
        return None

def generate_random_scenario_idea():
    """
    Asks the AI for a creative, unique premise for a game.
    """
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = """
    Generate a creative, intriguing, and specific premise for a text adventure game. 
    It can be sci-fi, fantasy, horror, or weird fiction.
    Keep it to one short sentence. 
    Example: "A noir detective searching for a stolen memory in a city floating on Venus."
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return "A time-traveler stuck in a loop during the fall of Rome."