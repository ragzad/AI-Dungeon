import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from utils import load_game, save_game

# Load environment variables
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def get_archivist_response(current_state, user_action):
    """
    Sends state + action to Gemini Flash and gets a JSON update back.
    """
    # We use Gemini 2.5 Flash for speed and logic
    model = genai.GenerativeModel('gemini-2.5-flash',
        generation_config={"response_mime_type": "application/json"})

    system_prompt = """
    You are the Archivist. You manage the JSON database.
    
    CRITICAL INSTRUCTION:
    Check the 'npcs' list in the Current State.
    If the user mentions a specific character name (e.g., "The Stranger", "The Orc") 
    that is NOT exactly in the 'npcs' keys, you MUST output this error:
    
    {"error": "target_missing", "target_name": "Exact Name User Said"}
    
    DO NOT invent a description. DO NOT pretend they are there.
    ONLY output the error if the name is missing.
    """

    prompt = f"""
    {system_prompt}
    
    CURRENT STATE:
    {json.dumps(current_state)}
    
    PLAYER ACTION:
    "{user_action}"
    """

    response = model.generate_content(prompt)
    
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        return {"error": "Failed to parse JSON from AI", "raw": response.text}

def update_world_state(updates):
    """
    Merges the AI's proposed updates into the actual world_state.json
    Now supports both direct structure matching (AI preference) and custom keys.
    """
    state = load_game()
    
    # 1. Handle Narrative Cue
    if "narrative_cue" in updates:
        print(f"\n[ARCHIVIST LOG]: {updates['narrative_cue']}")

    # 2. Update Player (Handles both specific deltas and direct overwrites)
    if "player" in updates:
        # The AI sent a direct update like {'player': {'hp': 20}}
        for key, val in updates['player'].items():
            state['player'][key] = val
            
    elif "player_update" in updates:
        # The AI followed the strict custom instructions
        p_up = updates['player_update']
        if "hp" in p_up: state['player']['hp'] = p_up['hp']
        if "inventory_add" in p_up:
            for item in p_up['inventory_add']: state['player']['inventory'].append(item)
        if "inventory_remove" in p_up:
            for item in p_up['inventory_remove']:
                if item in state['player']['inventory']: state['player']['inventory'].remove(item)

    # 3. Update NPCs (Handles both direct 'npcs' key and 'npc_updates')
    # We check for 'npcs' first because that's what your AI just generated.
    npc_source = updates.get("npcs") or updates.get("npc_updates")
    
    if npc_source:
        for npc_id, npc_data in npc_source.items():
            if npc_id in state['npcs']:
                for key, val in npc_data.items():
                    state['npcs'][npc_id][key] = val

    # 4. Update World Flags (New!)
    if "world_flags" in updates:
        for flag, val in updates['world_flags'].items():
            state['world_flags'][flag] = val

    # 5. Save
    save_game(state)
    return state