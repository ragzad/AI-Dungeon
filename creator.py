import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location, current_state=None):

    # 1. EXTRACT GENRE
    genre = "High Fantasy" # Default
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
    
def generate_genesis_location(genre):
    """
    Creates a starting location based on a genre.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    prompt = f"""
    You are the World Forger.
    The player is starting a new game in the Genre: {genre}.
    
    YOUR JOB:
    Create a detailed Starting Location (Hub).
    
    EXAMPLES:
    - Cyberpunk -> "Neon-Drenched Alley" or "Corporate Penthouse"
    - Pirate -> "The Captain's Quarters" or "Port Royal Docks"
    - Fantasy -> "The Old Tavern" or "King's Road"
    
    RULES:
    1. Give it a specific name.
    2. Visual Exits (not names).
    
    OUTPUT SCHEMA:
    {{
      "type": "location",
      "id": "gen_start_loc",
      "data": {{
        "name": "Name of Place",
        "description": "Atmospheric description.",
        "exits": ["Visual description of exit 1"],
        "suggested_exits": ["Visual description of exit 2"]
      }}
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return None