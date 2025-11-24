import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
# We use the Pro model for good prompt engineering
MODEL_NAME = 'models/gemini-2.5-flash' 
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def get_image_prompt(narrative_text):
    """
    Reads the story text and converts it into a stable diffusion/midjourney style prompt.
    """
    model = genai.GenerativeModel(MODEL_NAME)
    
    system_prompt = """
    You are an AI Art Director. 
    Your job is to read a story segment and output a Single Image Prompt that captures the essence of the scene.
    
    GUIDELINES:
    - Style: Dark Fantasy RPG Art, Oil Painting style, heavily detailed.
    - Format: purely descriptive keywords, comma-separated.
    - No filler text. Just the visual description.
    """
    
    prompt = f"""
    {system_prompt}
    
    STORY SEGMENT:
    "{narrative_text}"
    
    IMAGE PROMPT:
    """
    
    response = model.generate_content(prompt)
    return response.text.strip()

def generate_image(image_prompt):
    """
    PLACEHOLDER: Connecting to a real Image Gen API (DALL-E 3 or Imagen) requires a paid tier/credits.
    For this hackathon demo, we will return a placeholder or the prompt itself.
    
    If you have an OpenAI key, you can uncomment the code below to get real images.
    """
    # Option A: Return a static placeholder for testing

    # Option B: Return the prompt to display in the UI (The "Art Director" View)
    return image_prompt