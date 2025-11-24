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

    system_prompt = """
    You are the Dungeon Master. 
    
    INPUTS:
    1. World State
    2. Player Action (WHAT THE USER SAID)
    3. Archivist Log (The Outcome)
    
    YOUR JOB:
    Write the response to the player.
    
    RULES:
    1. DIRECTLY RESPOND to the "Player Action". If they said "Hello", have an NPC say "Hello" back.
    2. Do NOT just describe the room again. Advance the moment.
    3. Keep it under 3 sentences.
    4. Tone: Immersive, fantasy.
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