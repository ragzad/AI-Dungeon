import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def create_new_entity(target_name, current_location, current_state=None):
    # 1. CHECK THE SHADOW QUEUE
    if current_state and "shadow_queue" in current_state:
        queue = current_state["shadow_queue"]
        for index, entity in enumerate(queue):
            keywords = entity.get("keywords", [])
            # Fuzzy match
            if target_name.lower() in [k.lower() for k in keywords] or target_name.lower() in entity.get("data", {}).get("name", "").lower():
                print(f"✨ DREAMER HIT: Found {target_name} in cache!")
                current_state["shadow_queue"].pop(index)
                return entity

    # 2. GENERATE NEW
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
    1. **MATCH THE GENRE:** - Noir: Offices, alleys, bars.
       - Horror: Basements, attics, woods.
       - Fantasy: Dungeons, taverns.
    2. **SPATIAL LOGIC:** - If at a Kitchen, "Down" is likely a Cellar.
       - If in a Hallway, "Left" is a Bedroom.
    3. **VISUAL EXITS (CRITICAL):**
       - In 'suggested_exits', do NOT list names. List VISUAL DESCRIPTIONS.
       - Bad: "The Library"
       - Good: "A heavy oak door smelling of old paper."
    
    OUTPUT SCHEMA (Choose appropriate type):
    
    OPTION A (Location):
    {{
      "type": "location",
      "id": "gen_loc_{target_name.lower().replace(' ', '_')}",
      "data": {{
        "name": "{target_name} (Genre Appropriate Name)",
        "description": "Atmospheric description.",
        "exits": ["back to {current_location}"],
        "suggested_exits": ["A rusty ladder leading up", "A dark tunnel"]
      }}
    }}
    
    (Option B/C for NPC/Items follow standard schema)
    {{
      "type": "npc",
      "id": "...", "data": {{ "name": "...", "description": "...", "status": "alive" }}
    }}
    {{
      "type": "item",
      "item_name": "...", "data": {{ "description": "..." }}
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Creator Error: {e}")
        return None