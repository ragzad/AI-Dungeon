import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def narrate_scene(current_state, recent_action, archivist_log):
    model = genai.GenerativeModel(MODEL_NAME)

    # Filter State (Fog of War)
    visible_location = current_state.get("locations", {}).get(current_state.get("current_location_id"), {})
    
    story_state = current_state.get("story_state", {})
    direction = story_state.get("narrative_direction", "Describe the scene.")
    threat = story_state.get("active_threat", "None")
    beat = story_state.get("current_beat", "setup")
    tension = story_state.get("global_tension", 1)

    system_prompt = f"""
    You are a Dungeon Master (DM) playing a game with a friend.
    
    CONTEXT:
    - Director's Orders: "{direction}"
    - Current Threat: {threat}
    
    YOUR ATTITUDE:
    1. **YOU ARE NOT THE WORLD.** You are the storyteller. Do not get attached to your NPCs.
    2. **"YES, AND..."** : If the player says "I am a Space Ork," do not say "No you aren't, you are in a void." 
       - Say: "The void shatters around you! The illusion falls away. You stand in your heavy armor, holding a Choppa."
    3. **ADAPTABILITY:** If the player ignores a detail, drop it. If they focus on a detail, expand it.
    
    STRICT RULES:
    - Never block the player's creativity.
    - If the player contradicts the current scene, assume the scene was an illusion or a dream and move to the new reality.
    - Keep descriptions punchy and exciting.
    
    INPUTS:
    - Player Action: "{recent_action}"
    - Physical Result: "{archivist_log}"
    
    OUTPUT:
    A responsive, improvisational narrative response.
    """
    
    prompt = f"{system_prompt}"

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "The world shifts..."