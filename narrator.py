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
    You are the Dungeon Master (DM). You are running a tabletop RPG.
    
    Current Tension: {tension}/10.
    Director's Instruction: "{direction}"
    
    YOUR RULES:
    1. BE CONCISE. Do not write paragraphs of fluff. Get to the point.
    2. PRESENT A PROBLEM. If tension is high (>5), something should be hunting, blocking, or attacking the player RIGHT NOW.
    3. CALL TO ACTION. You MUST end your response by asking the player what they want to do.
    
    BAD RESPONSE:
    "The shadows swirl around you, whispering ancient secrets of a forgotten time, beautiful and haunting..." (Too passive).
    
    GOOD RESPONSE:
    "The shadows solidify into a clawed hand grabbing at your leg! The door is locked. Do you fight or try to pick the lock?"
    
    INPUTS:
    - Action: {recent_action}
    - Outcome: {archivist_log}
    
    OUTPUT:
    Write the DM's response. Be direct. Demand input.
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