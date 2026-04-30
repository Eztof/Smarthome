# ═══════════════════════════════════════════════════════════
#  core/database.py  –  SQLite Datenbanklogik
# ═══════════════════════════════════════════════════════════

import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def get_connection():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn   = get_connection()
    cursor = conn.cursor()

    # ── Wetter: Aktuelle Daten ───────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_current (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT NOT NULL,
            temperature   REAL, feels_like REAL, humidity INTEGER,
            wind_speed    REAL, wind_direction INTEGER,
            weather_code  INTEGER, description TEXT, is_day INTEGER
        )
    """)

    # ── Wetter: Stundendaten ─────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_hourly (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            date              TEXT NOT NULL,
            hour_time         TEXT NOT NULL,
            temperature       REAL, feels_like REAL, humidity INTEGER,
            wind_speed        REAL, precipitation_prob INTEGER,
            weather_code      INTEGER, description TEXT
        )
    """)

    # ── Wetter: Tagesprognose ────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_daily (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date    TEXT NOT NULL,
            forecast_date TEXT NOT NULL,
            temp_max REAL, temp_min REAL, precipitation REAL,
            weather_code INTEGER, description TEXT,
            sunrise TEXT, sunset TEXT,
            UNIQUE(fetch_date, forecast_date)
        )
    """)

    # ── Hunde: Ereignisse ────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dog_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL,
            db_level   REAL NOT NULL,
            duration_s REAL DEFAULT 0,
            threshold  REAL NOT NULL,
            wav_file   TEXT DEFAULT ''
        )
    """)
    # Spalten nachträglich hinzufügen falls DB schon existiert
    for col, typedef in [
        ("wav_file",    "TEXT DEFAULT ''"),
        ("sensor_name", "TEXT DEFAULT ''"),
        ("sensor_room", "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE dog_events ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # ── Einstellungen ────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Standardwerte
    defaults = {
        "dog_threshold": str(config.DOG_THRESHOLD_DB),
        "dog_device":    "default",
    }
    for k, v in defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v)
        )

    conn.commit()
    conn.close()
    print("OK: Datenbank bereit:", config.DB_PATH)


def get_setting(key: str, default=None):
    try:
        conn = get_connection()
        row  = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value)
    )
    conn.commit()
    conn.close()
