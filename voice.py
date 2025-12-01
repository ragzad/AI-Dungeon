import asyncio
import base64
import edge_tts
import tempfile
import os

# Voice Options mapped to Edge-TTS voices
# You can find more by running `edge-tts --list-voices` in terminal
VOICE_MAP = {
    'Puck': 'en-US-ChristopherNeural',  # Deep, warm
    'Fenrir': 'en-US-EricNeural',       # Deep, intense
    'Kore': 'en-US-AnaNeural',          # Soft, mysterious
    'Zephyr': 'en-US-GuyNeural'         # Balanced
}

async def _generate_audio_async(text, voice_name):
    """
    Internal async function to generate audio using Edge TTS.
    """
    voice = VOICE_MAP.get(voice_name, 'en-US-ChristopherNeural')
    communicate = edge_tts.Communicate(text, voice)
    
    # Save to a temporary file first
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        temp_filename = temp_file.name
    
    await communicate.save(temp_filename)
    
    # Read back as bytes
    with open(temp_filename, "rb") as f:
        audio_data = f.read()
        
    # Cleanup
    os.remove(temp_filename)
    
    return audio_data

def generate_voice_audio(text, voice_name="Puck"):
    """
    Generates audio using Edge TTS (wrapped synchronously for Streamlit).
    Returns: Base64 string of the audio.
    """
    try:
        # Run the async function synchronously
        audio_bytes = asyncio.run(_generate_audio_async(text, voice_name))
        
        # Convert to Base64 for the frontend
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        return audio_b64
        
    except Exception as e:
        print(f"Voice Error: {e}")
        return None