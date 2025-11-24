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
    Your job is to describe the scene to the player based STRICTLY on the provided data.
    
    GUIDELINES:
    1. Tone: Immersive, fantasy, slightly dark.
    2. Length: Keep it under 3 sentences (short and punchy).
    3. Use the 'Archivist Log' to know what just happened (combat, item pickup, etc).
    4. If an NPC is marked 'dead' or 'hostile', reflect that in the description.
    5. Do NOT output JSON. Output pure story text.
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