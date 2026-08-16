import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DOWNLOAD_DIR = os.getenv(
    "DOWNLOAD_DIR",
    os.path.join(os.path.expanduser("~"), "Music", "Fel7oMedia"),
).strip()
TEMP_DIR = os.getenv("TEMP_DIR", os.path.join(BASE_DIR, "temp")).strip()
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data")).strip()

for directory in (DOWNLOAD_DIR, TEMP_DIR, DATA_DIR):
    os.makedirs(directory, exist_ok=True)

# Secrets are intentionally required from the environment. Never add real values here.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@").strip()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:9876/callback"
).strip()

# Optional webhook mode for managed hosts. Leave WEBHOOK_URL empty for polling.
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram").strip() or "/telegram"
if not WEBHOOK_PATH.startswith("/"):
    WEBHOOK_PATH = "/" + WEBHOOK_PATH
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

try:
    ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0").strip() or "0")
except ValueError as exc:
    raise RuntimeError("ADMIN_CHAT_ID must be an integer Telegram chat ID.") from exc

DEFAULT_BITRATE = os.getenv("DEFAULT_BITRATE", "320").strip().lower()
if DEFAULT_BITRATE not in {"128", "320", "flac"}:
    DEFAULT_BITRATE = "320"

try:
    SPOTIFY_POLL_INTERVAL_SECONDS = max(
        int(os.getenv("SPOTIFY_POLL_INTERVAL_SECONDS", "21600")), 60
    )
except ValueError:
    SPOTIFY_POLL_INTERVAL_SECONDS = 21600

SPOTIFY_MONITOR_ENABLED = os.getenv(
    "SPOTIFY_MONITOR_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}


def validate_runtime_config() -> None:
    """Fail fast instead of silently using credentials committed to source control."""
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add the newly generated Telegram token "
            "as an environment variable before starting the bot."
        )
    if WEBHOOK_URL and not WEBHOOK_SECRET:
        raise RuntimeError(
            "WEBHOOK_SECRET is required when WEBHOOK_URL is configured."
        )


def spotify_is_configured() -> bool:
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)
