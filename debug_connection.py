import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("Testing connection to Gemini...")
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Say 'Hello' if you can hear me.")
    print(f"Success! AI said: {response.text}")
except Exception as e:
    print(f"Connection failed: {e}")