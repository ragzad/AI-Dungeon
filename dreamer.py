import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def dream_up_content(current_state):
    """
    Looks at the current story direction and pre-generates 
    entities that might be needed soon.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    # Extract context
    location_id = current_state.get("current_location_id")
    location = current_state["locations"].get(location_id, {})
    story = current_state.get("story_state", {})
    current_queue = current_state.get("shadow_queue", [])

    # Optimization: Don't dream if we already have plenty of ideas (Limit 5)
    if len(current_queue) >= 5:
        return []

    system_prompt = """
    You are The Dreamer. You operate in the background of a roleplaying game.
    
    YOUR JOB:
    Predict what the player might encounter next based on the current location and story mood.
    Generate 2-3 "Potential Entities" (NPCs, Items, or Locations).
    
    INPUTS:
    - Location: {location.get('name')} ({location.get('description')})
    - Narrative Mood: {story.get('narrative_direction')}
    
    OUTPUT SCHEMA:
    Return a LIST of JSON objects. Each object must look like a standard Entity (type, id, data).
    
    EXAMPLE:
    [
      { "type": "npc", "keywords": ["guard", "soldier"], "id": "gen_guard_01", "data": { "name": "Nervous Guard", ... } },
      { "type": "item", "keywords": ["sword", "weapon"], "item_name": "Rusty Blade", ... }
    ]
    """

    prompt = f"""
    {system_prompt}
    
    CONTEXT:
    Location: {location.get('name')}
    Mood: {story.get('narrative_direction')}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Dreamer Error: {e}")
        return []