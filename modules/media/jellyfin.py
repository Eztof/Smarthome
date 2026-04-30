# ═══════════════════════════════════════════════════════════
#  modules/media/jellyfin.py  –  Jellyfin-Integration
# ═══════════════════════════════════════════════════════════

import requests
import subprocess
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import config


def _headers():
    return {
        "X-Emby-Token": config.JELLYFIN_API_KEY,
        "Content-Type": "application/json",
    }


def get_status():
    """Gibt den aktuellen Jellyfin-Status zurueck."""
    result = {
        "running":    False,
        "url":        config.JELLYFIN_URL,
        "api_key_set": bool(config.JELLYFIN_API_KEY),
        "version":    None,
        "users":      0,
        "sessions":   0,
        "libraries":  [],
        "error":      None,
    }

    if not config.JELLYFIN_API_KEY:
        result["error"] = "Kein API-Key konfiguriert. Bitte in config.py eintragen."
        # Trotzdem prüfen ob Jellyfin erreichbar ist
        try:
            r = requests.get(f"{config.JELLYFIN_URL}/System/Info/Public", timeout=3)
            if r.status_code == 200:
                info = r.json()
                result["running"] = True
                result["version"] = info.get("Version", "?")
        except Exception:
            pass
        return result

    try:
        r = requests.get(
            f"{config.JELLYFIN_URL}/System/Info",
            headers=_headers(), timeout=5
        )
        r.raise_for_status()
        info = r.json()
        result["running"] = True
        result["version"] = info.get("Version", "?")
    except requests.ConnectionError:
        result["error"] = "Jellyfin nicht erreichbar. Ist der Dienst gestartet?"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

    # Aktive Sessions
    try:
        r = requests.get(
            f"{config.JELLYFIN_URL}/Sessions",
            headers=_headers(), timeout=3
        )
        sessions = r.json()
        result["sessions"] = len([s for s in sessions if s.get("NowPlayingItem")])
    except Exception:
        pass

    # Bibliotheken
    try:
        r = requests.get(
            f"{config.JELLYFIN_URL}/Library/VirtualFolders",
            headers=_headers(), timeout=3
        )
        libs = r.json()
        result["libraries"] = [
            {"name": lib.get("Name","?"), "type": lib.get("CollectionType","?")}
            for lib in libs
        ]
    except Exception:
        pass

    return result


def is_installed():
    """Prueft ob Jellyfin als Windows-Dienst installiert ist."""
    try:
        r = subprocess.run(
            ["sc", "query", "JellyfinServer"],
            capture_output=True, text=True, timeout=3
        )
        return "JellyfinServer" in r.stdout
    except Exception:
        return False


def start_service():
    try:
        subprocess.run(["net", "start", "JellyfinServer"],
                       capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def stop_service():
    try:
        subprocess.run(["net", "stop", "JellyfinServer"],
                       capture_output=True, timeout=10)
        return True
    except Exception:
        return False
