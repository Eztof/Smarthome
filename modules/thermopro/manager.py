# ═══════════════════════════════════════════════════════════
#  modules/thermopro/manager.py
#  Nur DB-Zugriff – kein bleak, kein asyncio
#  Der Scanner läuft als eigener Prozess (thermopro_scanner.py)
# ═══════════════════════════════════════════════════════════

import sys, os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from core.database import get_connection


def get_all() -> list[dict]:
    """Alle Geräte aus DB (inkl. offline-Geräte), neueste Werte."""
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT mac, name, room, last_seen, temperature, humidity, battery
            FROM thermopro_devices
            ORDER BY room, mac
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# Alias fuer routes.py
get_all_from_db = get_all


def get_history(mac: str, hours: int = 24) -> list[dict]:
    """Messverlauf der letzten N Stunden fuer ein Geraet."""
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_connection()
        rows = conn.execute("""
            SELECT timestamp, temperature, humidity, battery
            FROM thermopro_readings
            WHERE mac=? AND timestamp>=?
            ORDER BY timestamp ASC
        """, (mac, since)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[ThermoPro] History Fehler: {e}")
        return []


def rename_device(mac: str, room: str, name: str) -> bool:
    """Setzt Raum und Anzeigename fuer ein Geraet."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE thermopro_devices SET room=?, name=? WHERE mac=?",
            (room.strip(), name.strip(), mac)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[ThermoPro] Rename Fehler: {e}")
        return False


def is_online(mac: str, max_age_seconds: int = 90) -> bool:
    """Prueft ob ein Geraet zuletzt vor max_age_seconds gesehen wurde."""
    try:
        conn = get_connection()
        row  = conn.execute(
            "SELECT last_seen FROM thermopro_devices WHERE mac=?", (mac,)
        ).fetchone()
        conn.close()
        if not row or not row["last_seen"]:
            return False
        last = datetime.strptime(row["last_seen"], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - last).total_seconds() <= max_age_seconds
    except Exception:
        return False
