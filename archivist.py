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

    # Extract relevant NPC data for context
    loc_id = current_state.get("current_location_id")
    local_npcs = {k:v for k,v in current_state.get("npcs", {}).items() if v.get("location_id") == loc_id}

    system_prompt = """
    You are the Archivist. You manage the Game Logic and Physics.
    
    YOUR JOB:
    1. Analyze the 'Player Action' for Feasibility.
       - "I throw my ship" -> IMPOSSIBLE. Result: Failure.
       - "I rob him" -> POSSIBLE. Result: Combat/Hostility.
    2. Update NPC Attitudes.
       - If player attacks/robs -> Set NPC attitude to 'hostile'.
       - If player helps -> Set NPC attitude to 'friendly'.
    
    CRITICAL RULE - LOGIC CHECK:
    If the action is physically impossible, return a result indicating failure and mockery. Do NOT allow the action to succeed.
    
    CRITICAL RULE - EMOTIONAL PERMANENCE:
    If an NPC becomes 'hostile', they DO NOT help the player in the same turn.
    
    OUTPUT SCHEMA:
    {
      "narrative_cue": "Description of the physical outcome.",
      "npc_updates": { "npc_id": { "attitude": "hostile", "status": "active" } }
    }
    """

    prompt = f"""
    {system_prompt}
    CURRENT STATE: {json.dumps(current_state)}
    LOCAL NPCS: {json.dumps(local_npcs)}
    PLAYER ACTION: "{user_action}"
    """

    response = model.generate_content(prompt)
    
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        return {"narrative_cue": "The action fails to take hold on reality."}

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