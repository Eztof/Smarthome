# ═══════════════════════════════════════════════════════════
#  config.py  –  Zentrale Konfiguration
#  Hier alle Einstellungen anpassen
# ═══════════════════════════════════════════════════════════

import os

# ── Pfade ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "smarthome.db")
LOG_PATH = os.path.join(BASE_DIR, "data", "smarthome.log")

# ── Server ───────────────────────────────────────────────
HOST  = "0.0.0.0"   # Im gesamten Heimnetz erreichbar
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

# ── Hunde-Modul ──────────────────────────────────────────
DOG_THRESHOLD_DB   = 65      # Standard-Schwellenwert in dB
DOG_SAMPLERATE     = 44100
DOG_CHUNK_DURATION = 0.3     # Sekunden pro Messung
DOG_DEVICE_INDEX   = None    # None = Standard-Mikrofon
DOG_COOLDOWN       = 3.0     # Sekunden zwischen zwei Ereignissen

# ── Jellyfin (Mediaserver) ───────────────────────────────
JELLYFIN_URL     = "http://localhost:8096"
JELLYFIN_API_KEY = ""        # In Jellyfin unter: Dashboard → API-Keys

# ── AppDatabase ──────────────────────────────────────────
APPDB_HIDDEN_TABLES = ["sqlite_sequence"]  # Tabellen die nicht angezeigt werden
