import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-1.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location, current_state=None):
    # --- NO CACHE CHECK (Dreamer Removed) ---
    # We go straight to generation.

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
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Creator Error: {e}")
        return None