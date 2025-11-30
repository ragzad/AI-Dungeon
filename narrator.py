import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = 'models/gemini-2.5-flash' 

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def narrate_scene(current_state, recent_action, archivist_log):
    """
    Generates a story segment based on the current state and what just happened.
    """
    model = genai.GenerativeModel(MODEL_NAME)

    story_state = current_state.get("story_state", {})
    direction = story_state.get("narrative_direction", "Describe the scene.")
    tension = story_state.get("global_tension", 1)

    system_prompt = f"""
    You are the Dungeon Master. 
    
    VITAL INSTRUCTION:
    You have received a SECRET NOTE from the Story Director:
    "{direction}"
    
    You MUST steer the story in this direction while describing the scene.
    
    Current Tension Level: {tension}/10. (Adjust your writing style: 1 is relaxed, 10 is frantic/fast-paced).
    
    INPUTS:
    1. World State
    2. Player Action
    3. Archivist Log (Physical Events)
    
    OUTPUT:
    Immersive fantasy prose (Max 3-4 sentences).
    """

    prompt = f"""
    {system_prompt}
    
    CURRENT WORLD STATE:
    {current_state}
    
    PLAYER ACTION:
    "{recent_action}"
    
    RESULT OF ACTION (ARCHIVIST LOG):
    "{archivist_log}"
    """

    response = model.generate_content(prompt)
    return response.text