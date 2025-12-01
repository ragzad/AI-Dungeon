import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def scan_story_for_entities(story_text, current_state):
    """
    Scans the story for NEW entities that need to be made real.
    """
    model = genai.GenerativeModel(MODEL_NAME, 
        generation_config={"response_mime_type": "application/json"})

    system_prompt = """
    You are The Scribe. 
    
    YOUR JOB:
    Read the story text. If the Narrator introduced something NEW that isn't in the database yet, extract it.
    
    RULES:
    1. **NPCs:** Extract ANY named character interacting with the player (e.g., "Liam", "The Shopkeeper").
    2. **Items:** Extract items the player ACQUIRED.
    3. **Lore:** Extract secrets, facts, or QUEST UPDATES.
       - If the story mentions "The disappearance involves artifacts", log that as Lore.
    
    OUTPUT SCHEMA:
    {
      "new_items": ["Item Name"],
      "new_npcs": [{"name": "Name", "description": "Context", "presence": "physical"}],
      "new_lore": [{"topic": "Topic Name", "entry": "The specific detail or fact learned."}]
    }
    """

    prompt = f"""
    {system_prompt}
    STORY TEXT: "{story_text}"
    """
    
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception:
        return {}