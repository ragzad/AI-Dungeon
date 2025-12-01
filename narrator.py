import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def narrate_scene(current_state, recent_action, archivist_log):
    model = genai.GenerativeModel(MODEL_NAME)

    visible_location = current_state.get("locations", {}).get(current_state.get("current_location_id"), {})
    story_state = current_state.get("story_state", {})
    direction = story_state.get("narrative_direction", "Describe the surroundings.")
    active_events = [e for e in current_state.get("world_events", []) if e.get("status") == "active"]
    
    visible_npcs = []
    for n in current_state.get("npcs", {}).values():
        if n["location_id"] == current_state.get("current_location_id"):
            visible_npcs.append(f"- {n['name']} ({n.get('attitude', 'neutral')})")
            
    system_prompt = f"""
    You are the Dungeon Master.
    
    PLAYER ACTION: "{recent_action}"
    
    *** CRITICAL OUTCOME (MUST INCLUDE THIS): ***
    "{archivist_log}"
    *********************************************
    
    CONTEXT:
    - Location: {visible_location.get("name", "Unknown")} ({visible_location.get("description", "")})
    - DM Instruction: "{direction}"
    - Visible NPCs: {visible_npcs}
    
    GUIDELINES:
    1. **PRIORITIZE THE OUTCOME:** The 'Critical Outcome' above comes from the game physics engine. If it says the player found 'Void Kin' lore, you MUST describe that discovery in detail. Do not summarize it away.
    2. **ATMOSPHERE:** Be concrete. Describe sights, sounds, and smells.
    3. **INTERACTIVITY:** End by hinting at what else the player can do.
    4. **BREVITY:** Keep it punchy (3-4 sentences max), but do not cut out the Critical Outcome details.
    """
    
    try:
        response = model.generate_content(system_prompt)
        return response.text
    except Exception:
        return "The world is silent."