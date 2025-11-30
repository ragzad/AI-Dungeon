import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from utils import load_game, save_game

load_dotenv()
model_name = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def get_archivist_response(current_state, user_action):
    model = genai.GenerativeModel(model_name,
        generation_config={"response_mime_type": "application/json"})

    system_prompt = """
    You are the Archivist. You manage the Game State.
    
    YOUR JOB:
    1. Analyze the action.
    2. Check for missing targets (NPCs/Locations/Items).
    3. If valid, output a JSON object with the changes.
    
    CRITICAL RULE - MISSING TARGETS:
    If the user mentions a target NOT in the current state:
    RETURN: {"error": "target_missing", "target_name": "The Name"}
    
    CRITICAL RULE - CONVERSATION:
    If the user talks, you MUST return a "narrative_cue" explaining the result.
    Do NOT return empty JSON.
    """

    prompt = f"""
    {system_prompt}
    CURRENT STATE: {json.dumps(current_state)}
    PLAYER ACTION: "{user_action}"
    """

    response = model.generate_content(prompt)
    
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        return {"narrative_cue": "The world reacts silently."}

def update_world_state(updates):
    state = load_game()
    
    if "player_update" in updates:
        pass
    if "narrative_cue" in updates:
        pass 
    if "narrative_cue" in updates: print(f"Log: {updates['narrative_cue']}")
    
    if "player" in updates:
        for k, v in updates['player'].items(): state['player'][k] = v
    if "player_update" in updates:
        p = updates['player_update']
        if "hp" in p: state['player']['hp'] = p['hp']
        if "inventory_add" in p: 
            for i in p['inventory_add']: state['player']['inventory'].append(i)
            
    # Handle NPCs
    npc_source = updates.get("npcs") or updates.get("npc_updates")
    if npc_source:
        for nid, ndata in npc_source.items():
            if nid in state['npcs']:
                for k, v in ndata.items(): state['npcs'][nid][k] = v

    save_game(state)
    return state