import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
def create_new_entity(target_name, current_location, current_state=None):
    """
    Generates a new NPC, Item, OR Location.
    NOW CHECKS THE SHADOW QUEUE FIRST.
    """
    
    # 1. CHECK THE SHADOW QUEUE (The Cache)
    if current_state and "shadow_queue" in current_state:
        queue = current_state["shadow_queue"]
        # Simple fuzzy match: is the target name inside the pre-generated keywords?
        for index, entity in enumerate(queue):
            keywords = entity.get("keywords", [])
            # Check if target_name is in keywords OR if target_name is very similar to the entity name
            if target_name.lower() in [k.lower() for k in keywords] or target_name.lower() in entity.get("data", {}).get("name", "").lower():
                print(f"✨ DREAMER HIT: Found {target_name} in cache!")
                
                # Remove from queue so we don't use it twice
                current_state["shadow_queue"].pop(index)
                return entity

    # 2. IF NOT FOUND, GENERATE FROM SCRATCH (The Old Way)
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})
    
    prompt = f"""
    You are the World Forger. 
    The player is trying to interact with '{target_name}'.
    
    CONTEXT:
    - Player is currently at: {current_location}
    
    RULES FOR LOCATIONS:
    1. NEVER name a location "Outside", "The Outside", or "Exit". Give it a name (e.g., "The Streets of Oakhaven", "Mistwood Forest").
    2. If creating a Location, you MUST include 'suggested_exits' in the data.
    3. 'suggested_exits' should be a list of 2-3 exciting places connected to this new location (e.g., ["Old Church", "Market District"]).
    
    OUTPUT SCHEMA (Choose one):
    
    OPTION C (Location):
    {{
      "type": "location",
      "id": "generated_loc_{target_name.lower().replace(' ', '_')}",
      "data": {{
        "name": "{target_name} (Thematic Name)",
        "description": "A vivid description of the area.",
        "exits": ["back to {current_location}"], 
        "suggested_exits": ["Place A", "Place B"] 
      }}
    }}
    
    (Options A (NPC) and B (Item) remain the same...)
    """
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Creator Error: {e}")
        return None