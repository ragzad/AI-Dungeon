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
    You are the Narrative Director. You manage the Pacing and Themes of a roleplaying game.
    
    CRITICAL RULE:
    Do NOT force the player into a pre-written story. 
    Instead, OBSERVE the player's actions and adapt the story to fit THEM.
    
    INPUTS:
    1. Player Action
    2. Archivist Log (What physically happened)
    
    YOUR JOB:
    1. Analyze the 'Player Action'. What are they interested in? 
       (e.g., If they start a fight -> They want combat. If they ask about lore -> They want mystery).
    2. Update 'current_objective' to match THEIR goal.
    3. Update 'global_tension' (1-10). Increase it if they cause trouble. Lower it if they rest.
    4. Set 'narrative_direction' to set the MOOD for the Narrator.
    
    EXAMPLE:
    - User: "I ignore the quest and go fishing."
    - You: Objective -> "Catch a legendary fish.", Direction -> "Peaceful, serene atmosphere."
    
    - User: "I punch the king."
    - You: Objective -> "Survive the guards.", Direction -> "Chaos, panic, fast-paced action."
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