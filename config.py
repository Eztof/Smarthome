# ═══════════════════════════════════════════════════════════
#  config.py  –  Zentrale Konfiguration
# ═══════════════════════════════════════════════════════════

import os

# ── Pfade ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "smarthome.db")
LOG_PATH = os.path.join(BASE_DIR, "data", "smarthome.log")

# ── Server ───────────────────────────────────────────────
HOST  = "0.0.0.0"
PORT  = 5000
DEBUG = False

# ── Zeitzone ─────────────────────────────────────────────
TIMEZONE = "Europe/Berlin"

# ── Standort (Wetter) ────────────────────────────────────
LOCATION_NAME = "Bünde"
LATITUDE      = 52.1989
LONGITUDE     = 8.5836

# ── Wetter ───────────────────────────────────────────────
WEATHER_UPDATE_INTERVAL = 5   # Minuten

# ── Wetter-Chart Darstellung ─────────────────────────────
WEATHER_RAIN_OPACITY_TOP = 0.55
WEATHER_RAIN_OPACITY_BTM = 0.08
WEATHER_RAIN_BORDER      = 0.6
WEATHER_TEMP_OPACITY     = 0.32

# ── Hunde-Modul ──────────────────────────────────────────
DOG_THRESHOLD_DB   = 65
DOG_SAMPLERATE     = 44100
DOG_CHUNK_DURATION = 0.3
DOG_DEVICE_INDEX   = None
DOG_COOLDOWN       = 3.0

# ── Jellyfin (Mediaserver) ───────────────────────────────
JELLYFIN_URL     = "http://localhost:8096"
JELLYFIN_API_KEY = ""

# ── AppDatabase ──────────────────────────────────────────
APPDB_HIDDEN_TABLES = ["sqlite_sequence"]
