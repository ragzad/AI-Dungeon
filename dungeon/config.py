import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "ai_dungeon"
ROOT = Path(__file__).resolve().parent.parent

# The Game Master runs on the Live API. If the first model can't connect
# (quota, not enabled on the key) the next one is tried.
LIVE_MODELS = [m for m in (os.getenv("LIVE_MODEL", "gemini-3.8-live"),
                           os.getenv("LIVE_FALLBACK_MODEL", "gemini-3.1-flash-live-preview")) if m]
# Used for the Game Master when no Live model is available, streamed over SSE.
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.5-flash-lite")
# Dialogue, Creator and Scribe are short structured calls, so they get a lite model.
BACKGROUND_MODEL = os.getenv("BACKGROUND_MODEL", "gemini-3.1-flash-lite")
BACKGROUND_FALLBACK = os.getenv("BACKGROUND_FALLBACK_MODEL", "gemini-3.5-flash-lite")
VOICE = os.getenv("GM_VOICE", "Charon")

SAVE_DIR = Path(os.getenv("SAVE_DIR", ROOT / "saves"))
CACHE_DIR = Path(os.getenv("CACHE_DIR", ROOT / ".cache"))

# fallback chain used when a model returns 429
FALLBACKS = {BACKGROUND_MODEL: BACKGROUND_FALLBACK, TEXT_MODEL: BACKGROUND_MODEL}


def has_key():
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
