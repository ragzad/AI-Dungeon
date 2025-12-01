import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

# Voice Options:
# 'Puck' - Deep, warm, slightly gruff (Best for Narrator)
# 'Fenrir' - Deep, intense (Good for Horror)
# 'Kore' - Softer, mysterious
# 'Zephyr' - Balanced, standard

def generate_voice_audio(text, voice_name="Puck"):
    """
    Generates audio using Gemini's Speech API (REST method for stability).
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": text}]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name
                    }
                }
            }
        }
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        # Extract Audio Data
        data = response.json()
        audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        return audio_b64
        
    except Exception as e:
        print(f"Voice Error: {e}")
        return None