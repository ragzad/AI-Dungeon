import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def update_story_state(current_state, player_action, archivist_log):
    """
    Analyzes the game flow and updates the Narrative Arc based on player choices.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    # Load existing story state or create a default one
    story = current_state.get("story_state", {
        "current_act": 1,
        "global_tension": 2,
        "current_objective": "Explore the world and find your path.",
        "narrative_direction": "The world is open. React to the player's curiosity."
    })
    
    system_prompt = """
    You are the Narrative Director. Your job is to throw obstacles at the player.
    
    CRITICAL RULE:
    Do not just describe moods. COMMAND EVENTS.
    
    If the player is moving -> "Throw an obstacle in their path."
    If the player is investigating -> "Reveal a clue but trigger a trap."
    If the player is fighting -> "Escalate the danger."
    
    INPUTS:
    - Player Action: "{player_action}"
    - Current Objective: "{story.get('current_objective')}"
    
    YOUR OUTPUT JSON MUST UPDATE:
    1. 'narrative_direction': A specific instruction to the DM (e.g., "The roof collapses. Ask for a dexterity check.").
    2. 'current_objective': Update based on player focus.
    3. 'global_tension': Increase it if the player is stalling or in danger.
    """
    
    prompt = f"""
    {system_prompt}
    
    CURRENT STORY STATE:
    {json.dumps(story)}
    
    PLAYER ACTION:
    "{player_action}"
    
    WHAT JUST HAPPENED:
    "{archivist_log}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Director Error: {e}")
        return story