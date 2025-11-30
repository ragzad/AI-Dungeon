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
    world_events = current_state.get("world_events", [])
    active_events = [e for e in world_events if e.get("status") == "active"]

    events_context = "\n".join([f"- {e['name']}: {e['description']}" for e in active_events])

    player_view = {
        "visible_npcs": [f"{n['name']} ({n.get('attitude', 'neutral')})" for n in current_state.get("npcs", {}).values() 
                         if n["location_id"] == current_state.get("current_location_id")]
    }

    system_prompt = f"""
    You are a Dungeon Master (DM) playing a game with a friend.
    
    CONTEXT:
    - Director's Orders: "{direction}"
    - Current Threat: {threat}
    - CURRENT SITUATION (Include these in the scene!):{events_context}
    YOUR ATTITUDE:
    1. **YOU ARE NOT THE WORLD.** You are the storyteller. Do not get attached to your NPCs.
    2. **"YES, AND..."** : If the player says "I am a Space Ork," do not say "No you aren't, you are in a void." 
       - Say: "The void shatters around you! The illusion falls away. You stand in your heavy armor, holding a Choppa."
    3. **ADAPTABILITY:** If the player ignores a detail, drop it. If they focus on a detail, expand it.
    
    STRICT RULES:
    - If there are multiple active events, weave them together.
    - Maintain continuity.
    - Never block the player's creativity.
    - If the player contradicts the current scene, assume the scene was an illusion or a dream and move to the new reality.
    - Keep descriptions punchy and exciting.
    - Ensure character relations are consistent
    
    INPUTS:
    - Player Action: "{recent_action}"
    - Physical Result: "{archivist_log}"
    - Visible World: {json.dumps(player_view)}
    
    OUTPUT:
    A responsive, improvisational narrative response.
    """
    
    prompt = f"{system_prompt}"

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "The world shifts..."