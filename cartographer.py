import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
import graphviz

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def get_map_update(current_state, player_action):
    """
    Analyzes movement/travel intentions.
    """
    model = genai.GenerativeModel(MODEL_NAME, generation_config={"response_mime_type": "application/json"})
    
    loc_id = current_state.get("current_location_id")
    locations = current_state.get("locations", {})
    current_loc = locations.get(loc_id, {})
    
    # Context: Where are we and where can we go?
    known_exits = current_loc.get("exits", [])
    
    system_prompt = f"""
    You are the Cartographer. Detect MOVEMENT.
    
    CURRENT LOCATION: {current_loc.get('name')} (ID: {loc_id})
    KNOWN EXITS: {known_exits}
    
    PLAYER ACTION: "{player_action}"
    
    YOUR JOB:
    1. Detect if the player is trying to MOVE.
    2. Determine the Destination.
    3. Describe the Journey proactively.
    
    OUTPUT SCHEMA:
    {{
      "is_movement": boolean,
      "destination_name": "Name of target",
      "travel_type": "local" (walking nearby) or "journey" (fast travel/long distance),
      "travel_description": "A VIVID, ATMOSPHERIC sentence describing the route. Mention lighting, weather, sounds, or the vibe of the transition. Do NOT simply say 'You walk there'."
    }}
    """
    
    try:
        response = model.generate_content(system_prompt)
        return json.loads(response.text)
    except:
        return {"is_movement": False}

def generate_travel_event(route_description):
    """
    Generates a random encounter for a journey.
    """
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"Generate a short, 1-sentence travel event/obstacle for a journey along: {route_description}. Example: 'A sudden landslide blocks the path.' or 'You meet a traveling merchant.'"
    try:
        return model.generate_content(prompt).text.strip()
    except:
        return "The journey is long and quiet."

def render_map(current_state):
    """
    Visualizes the world graph.
    """
    graph = graphviz.Digraph()
    graph.attr(rankdir='LR', size='10', bgcolor='transparent')
    graph.attr('node', fontname='Helvetica', shape='box', style='filled', color='black', fillcolor='#f0f2f6')
    
    curr_id = current_state.get("current_location_id")
    
    for lid, loc in current_state.get("locations", {}).items():
        # Highlight current location
        fill = '#ffcccc' if lid == curr_id else '#e1e4e8'
        graph.node(lid, label=loc["name"], fillcolor=fill)
        
        # Draw connections
        for exit_name in loc.get("exits", []):
            pass
            
    return graph