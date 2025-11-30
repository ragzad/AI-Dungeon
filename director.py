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
    current_events = current_state.get("world_events", [])
    
    # Extract Location Context
    loc_id = current_state.get("current_location_id")
    loc_name = current_state.get("locations", {}).get(loc_id, {}).get("name", "Unknown")

    local_npcs = [npc for npc in current_state.get("npcs", {}).values() if npc.get("location_id") == loc_id]
    hostile_present = any(npc.get("attitude") == "hostile" for npc in local_npcs)

    system_prompt = f"""
    You are the Narrative Director.
    
    CURRENT CONTEXT:
    - Hostiles Nearby: {hostile_present}
    
    CRITICAL RULE - TONE CONSISTENCY:
    1. **NO MOOD SWINGS:** If the player just attacked someone, the NPC must NOT act friendly immediately.
    2. **PRIORITIZE LOCAL CONFLICT:** If the player is in a fight/argument (Local Conflict), do NOT resolve it just to advance the Global Plot.
       - Bad: "The merchant ignores that you punched him and points out the ship."
       - Good: "The merchant screams for guards, ignoring the ship on the horizon."
    3. **HANDLE NONSENSE:** If the player does something stupid ("Throw ship"), the world should react with confusion or disdain, NOT acceptance.
    
    INPUTS:
    - Player Action: "{player_action}"
    - Outcome: "{archivist_log}"
    
    OUTPUT JSON:
    1. 'narrative_direction': "The merchant backs away, terrified of the crazy pirate." (Logic first, Plot second).
    2. 'current_objective': "Escape the angry merchant."
    """
    
    prompt = f"""
    {system_prompt}
    CURRENT LOCATION: {loc_name}
    PLAYER ACTION: "{player_action}"
    WHAT JUST HAPPENED: "{archivist_log}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Director Error: {e}")
        # Return structure that keeps existing state safe
        return {"story_state": story, "world_events": current_events}