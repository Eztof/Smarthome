# ═══════════════════════════════════════════════════════════
#  thermopro_scanner.py  –  Eigenständiger BLE-Scanner
#  Läuft als separater Prozess, schreibt direkt in SQLite
#  Kein Eventlet – reines asyncio
# ═══════════════════════════════════════════════════════════

import asyncio
import sqlite3
import sys
import os
import time
from datetime import datetime

# Pfad zum Projektverzeichnis
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config

# ── Datenbankpfad direkt aus config ─────────────────────
DB_PATH      = config.DB_PATH
SAVE_INTERVAL = 60   # Sekunden zwischen zwei Messeinträgen pro Gerät

_last_saved: dict[str, float] = {}


# ── SQLite direkt (kein Flask/Eventlet) ─────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_tables():
    """Tabellen anlegen falls noch nicht vorhanden."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thermopro_devices (
            mac TEXT PRIMARY KEY, name TEXT DEFAULT '', room TEXT DEFAULT '',
            last_seen TEXT, temperature REAL, humidity INTEGER, battery INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thermopro_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mac TEXT NOT NULL,
            timestamp TEXT NOT NULL, temperature REAL, humidity INTEGER, battery INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_tp_readings_mac_ts
        ON thermopro_readings (mac, timestamp)
    """)
    conn.commit()
    conn.close()


def upsert_device(mac: str, ble_name: str, temperature: float,
                  humidity: int, battery: int):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO thermopro_devices
                (mac, name, room, last_seen, temperature, humidity, battery)
            VALUES (?, ?, '', ?, ?, ?, ?)
        """, (mac, ble_name, ts, temperature, humidity, battery))
        conn.execute("""
            UPDATE thermopro_devices
            SET last_seen=?, temperature=?, humidity=?, battery=?
            WHERE mac=?
        """, (ts, temperature, humidity, battery, mac))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[TP357] DB upsert Fehler: {e}", flush=True)


def save_reading(mac: str, temperature: float, humidity: int, battery: int):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO thermopro_readings (mac, timestamp, temperature, humidity, battery)
            VALUES (?, ?, ?, ?, ?)
        """, (mac, ts, temperature, humidity, battery))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[TP357] DB reading Fehler: {e}", flush=True)


# ── TP357 Advertisement-Parser ───────────────────────────

def parse_tp357(device, advertisement_data):
    """
    Parst BLE-Advertisementdaten des TP357.
    Gibt (temperature, humidity, battery) zurück oder None.
    """
    try:
        mfr = advertisement_data.manufacturer_data
        if not mfr:
            return None

        raw = None
        for cid, data in mfr.items():
            if cid == 0xEC88:
                raw = data
                break

        if raw is None and len(mfr) == 1:
            raw = list(mfr.values())[0]

        if raw is None or len(raw) < 6:
            return None

        temp_raw    = int.from_bytes(raw[2:4], byteorder="big", signed=True)
        temperature = round(temp_raw / 10.0, 1)
        humidity    = int(raw[4])
        battery_raw = int(raw[5])
        battery     = battery_raw if battery_raw <= 100 else round(battery_raw / 10)

        if not (-40 <= temperature <= 85):
            return None
        if not (0 <= humidity <= 100):
            return None

        return temperature, humidity, battery

    except Exception as e:
        print(f"[TP357] Parse-Fehler ({getattr(device,'name','')}): {e}", flush=True)
        return None


# ── Asyncio BLE-Scan ─────────────────────────────────────

async def run_scanner():
    from bleak import BleakScanner

    def callback(device, adv):
        name = device.name or ""
        if not (name.startswith("TP357") or name.startswith("TP358")
                or name.startswith("TP359")):
            return

        result = parse_tp357(device, adv)
        if result is None:
            return

        temperature, humidity, battery = result
        mac = device.address
        now = time.time()

        print(
            f"[TP357] {name} ({mac}) "
            f"T={temperature}°C  H={humidity}%  B={battery}%",
            flush=True,
        )

        upsert_device(mac, name, temperature, humidity, battery)

        last = _last_saved.get(mac, 0)
        if now - last >= SAVE_INTERVAL:
            save_reading(mac, temperature, humidity, battery)
            _last_saved[mac] = now

    print("[ThermoPro] BLE-Scanner läuft…", flush=True)

    while True:
        try:
            async with BleakScanner(detection_callback=callback):
                await asyncio.sleep(30)
        except Exception as e:
            print(f"[ThermoPro] Fehler: {e} – Neustart in 15s", flush=True)
            await asyncio.sleep(15)


# ── Einstieg ─────────────────────────────────────────────

if __name__ == "__main__":
    ensure_tables()
    try:
        asyncio.run(run_scanner())
    except KeyboardInterrupt:
        print("[ThermoPro] Scanner beendet.", flush=True)
