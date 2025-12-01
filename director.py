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
    current_objective = story.get("current_objective", "Explore")
    
    system_prompt = f"""
    You are the Narrative Director. You control the Pacing and Objectives of the game.
    
    CURRENT STATE:
    - Objective: "{current_objective}"
    - Genre: {story.get("genre", "Unknown")}
    - Tension Level: {story.get("global_tension", 1)}/10
    
    PLAYER INPUT:
    - Action: "{player_action}"
    - Consequence: "{archivist_log}"
    
    YOUR TASK:
    1. Analyze if the Player's Action has ADVANCED or CHANGED the Current Objective.
    2. If the player is asking questions ("Who is here?", "Look around"), set the 'narrative_direction' to REVEAL details.
    3. If the player is acting ("Attack", "Run"), set 'narrative_direction' to RESOLVE action.
    
    OBJECTIVE LOGIC:
    - If the player fulfilled the current objective -> CREATE A NEW OBJECTIVE immediately.
    - If the player is ignoring the objective -> ADAPT the objective to the players intent.
    
    OUTPUT SCHEMA:
    {{
      "current_objective": "Updated short-term goal (Max 10 words)",
      "narrative_direction": "Instruction for the Narrator (e.g. 'Describe the monster appearing', 'Reveal a hidden door')",
      "global_tension": Integer (1-10),
      "world_events": [] 
    }}
    """
    
    try:
        response = model.generate_content(system_prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Director Error: {e}")
        return {
            "current_objective": current_objective,
            "narrative_direction": "Describe the scene.",
            "global_tension": 1
        }