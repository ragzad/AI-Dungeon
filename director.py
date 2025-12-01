import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def update_story_state(current_state, player_action, archivist_log):
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    story = current_state.get("story_state", {})
    current_genre = story.get("genre", "adaptive")
    
    # Check if we are currently in the void
    in_void = current_state.get("current_location_id") == "loc_start"

    system_prompt = f"""
    You are the Narrative Director.
    
    CURRENT GENRE: {current_genre}
    IN VOID: {in_void}
    
    YOUR JOB:
    Detect if the player is defining the setting/genre.
    
    CRITICAL RULE - GENESIS:
    If the player defines who they are AND we are in the Void:
    1. Set 'trigger_genesis': true
    2. Set 'new_genre': The specific genre 
    3. Set 'narrative_direction': "Describe the new setting."
    
    INPUTS:
    - Player Action: "{player_action}"
    
    OUTPUT JSON:
    {{
      "genre": "...",
      "narrative_direction": "...",
      "current_objective": "...",
      "global_tension": 1,
      "trigger_genesis": boolean  <-- THIS IS THE KEY
    }}
    """
    
    prompt = f"{system_prompt}"
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Director Error: {e}")
        return story