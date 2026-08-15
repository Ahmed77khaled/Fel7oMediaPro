import os
from dotenv import load_dotenv

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Music", "Fel7oMedia")
TEMP_DIR     = os.path.join(BASE_DIR, "temp")
DATA_DIR     = os.path.join(BASE_DIR, "data")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR,     exist_ok=True)
os.makedirs(DATA_DIR,     exist_ok=True)

BOT_TOKEN             = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME          = os.getenv("BOT_USERNAME", "").lstrip("@").strip()
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:9876/callback").strip()
ADMIN_CHAT_ID         = int(os.getenv("ADMIN_CHAT_ID", "0"))
DEFAULT_BITRATE       = os.getenv("DEFAULT_BITRATE", "flac").strip().lower()
SPOTIFY_POLL_INTERVAL_SECONDS = max(int(os.getenv("SPOTIFY_POLL_INTERVAL_SECONDS", "21600")), 60)
SPOTIFY_MONITOR_ENABLED = os.getenv("SPOTIFY_MONITOR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def validate_runtime_config():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to the .env file before starting the bot.")


def spotify_is_configured() -> bool:
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)
