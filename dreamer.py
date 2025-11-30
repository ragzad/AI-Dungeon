import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def dream_up_content(current_state):
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    # Extract context
    location_id = current_state.get("current_location_id")
    location = current_state["locations"].get(location_id, {})
    story = current_state.get("story_state", {})
    current_queue = current_state.get("shadow_queue", [])

    if len(current_queue) >= 5: return []

    system_prompt = """
    You are The Dreamer.
    
    YOUR JOB:
    Predict what the player might encounter next based on the location and genre.
    
    OUTPUT SCHEMA:
    Return a LIST of JSON objects (npcs, items, or locations).
    Add "keywords" list to each for matching.
    """

    prompt = f"""
    {system_prompt}
    LOCATION: {location.get('name')}
    GENRE: {story.get('genre')}
    MOOD: {story.get('narrative_direction')}
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        return []