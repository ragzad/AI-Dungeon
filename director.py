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
    current_beat = story.get("current_beat", "setup")
    genre = story.get("genre", "adaptive")

    system_prompt = f"""
    You are the Narrative Director of a Tabletop RPG.
    
    Current Genre: {genre}
    
    THE GOLDEN RULE: 
    **THE PLAYER'S ENJOYMENT IS THE ONLY METRIC THAT MATTERS.**
    
    YOUR JOB:
    You are not simulating a physics engine. You are facilitating a story. 
    If the player wants to change the genre, setting, or tone: **LET THEM.**
    
    HANDLING "RETCONS":
    - If the player ignores your plot hook
      1. DO NOT try to force them back
      2. **ACCEPT THE PIVOT.** Immediately switch the genre and objective to match the player's new idea.
    
    INPUTS:
    - Player Action: "{player_action}"
    
    OUTPUT JSON:
    1. 'genre': Update this immediately if the player implies a new setting.
    2. 'narrative_direction': Tell the DM to adapt. 
       - Bad: "The Dream Seer is angry you ignored him."
       - Good: "The player wants to play Warhammer 40k. Fade out the Void. Fade in a rusty spaceship interior."
    3. 'active_threat': Create a new threat that fits the NEW genre.
    """
    
    prompt = f"{system_prompt}"
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Director Error: {e}")
        return story