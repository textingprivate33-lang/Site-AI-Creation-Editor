import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).parent
WORK = BASE / "work"
OUTPUT = BASE / "output"
MUSIC = BASE / "assets" / "music"
for _p in (WORK, OUTPUT, MUSIC):
    _p.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-US-AndrewNeural").strip()

WIDTH, HEIGHT, FPS = 1920, 1080, 25

# Contact details shown on the last scene. Add one line per channel to your .env file.
CONTACT_FIELDS = [("EMAIL", "Email"), ("WHATSAPP", "WhatsApp"), ("TELEGRAM", "Telegram"),
                  ("TIKTOK", "TikTok"), ("FACEBOOK", "Facebook"), ("INSTAGRAM", "Instagram")]
CONTACTS = [(label, os.getenv("CONTACT_" + key, "").strip())
            for key, label in CONTACT_FIELDS if os.getenv("CONTACT_" + key, "").strip()]
