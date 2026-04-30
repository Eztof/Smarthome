# ═══════════════════════════════════════════════════════════
#  modules/sensors/manager.py
#  Verwaltet verbundene Handy-Sensoren per WebSocket
# ═══════════════════════════════════════════════════════════

import threading
import time
import numpy as np
import wave
import os
import base64
from collections import deque
from datetime import datetime
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import config
from core.database import get_connection

RECORDINGS_DIR = os.path.join(os.path.dirname(config.DB_PATH), "aufnahmen")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

PRE_SECS  = 10
POST_SECS = 10
MAX_FILES = 200

# ── Sensor-Registry ───────────────────────────────────────
# { sid: { name, room, db, peak, threshold, connected_at,
#          ring_buffer, post_buffer, event_start, recording } }
_lock    = threading.Lock()
_sensors = {}


# ── Öffentliche API ───────────────────────────────────────

def register(sid: str, name: str, room: str, threshold: float):
    with _lock:
        _sensors[sid] = {
            "sid":          sid,
            "name":         name,
            "room":         room,
            "db":           0.0,
            "peak":         0.0,
            "threshold":    threshold,
            "connected_at": datetime.now().strftime("%H:%M:%S"),
            "recording":    False,
            "error":        None,
            # Ringpuffer (float32-chunks)
            "_ring":        deque(maxlen=_pre_chunks()),
            "_post":        [],
            "_post_rem":    0,
            "_pre_snap":    [],
            "_evt_start":   None,
            "_evt_peak":    0.0,
            "_last_evt":    0.0,
            "_samplerate":  16000,
        }
    print(f"[Sensor] Verbunden: {name} ({room})  sid={sid}")


def unregister(sid: str):
    with _lock:
        s = _sensors.pop(sid, None)
    if s:
        print(f"[Sensor] Getrennt: {s['name']} ({s['room']})")


def get_all():
    with _lock:
        return [
            {
                "sid":          s["sid"],
                "name":         s["name"],
                "room":         s["room"],
                "db":           round(s["db"], 1),
                "peak":         round(s["peak"], 1),
                "threshold":    s["threshold"],
                "connected_at": s["connected_at"],
                "recording":    s["recording"],
            }
            for s in _sensors.values()
        ]


def get_count():
    with _lock:
        return len(_sensors)


def set_threshold(sid: str, threshold: float):
    with _lock:
        if sid in _sensors:
            _sensors[sid]["threshold"] = threshold


def reset_peak(sid: str):
    with _lock:
        if sid in _sensors:
            _sensors[sid]["peak"] = 0.0


def _pre_chunks(samplerate=16000, chunk_dur=0.1):
    return int(PRE_SECS / chunk_dur)


# ── Audio-Chunk verarbeiten (vom WebSocket aufgerufen) ────

def process_audio_chunk(sid: str, audio_b64: str, samplerate: int = 16000):
    """
    Empfängt einen base64-kodierten Float32-Audio-Chunk vom Handy,
    berechnet dB, aktualisiert Ringpuffer, löst ggf. Aufnahme aus.
    """
    with _lock:
        if sid not in _sensors:
            return
        s = _sensors[sid]

    try:
        # Base64 → float32 numpy array
        raw   = base64.b64decode(audio_b64)
        chunk = np.frombuffer(raw, dtype=np.float32).copy()
        if len(chunk) == 0:
            return

        rms = float(np.sqrt(np.mean(chunk ** 2)))
        db  = _rms_to_db(rms)

        with _lock:
            s["db"]         = db
            s["_samplerate"] = samplerate
            if db > s["peak"]:
                s["peak"] = db
            threshold = s["threshold"]

            # Ringpuffer
            s["_ring"].append(chunk)

            now = time.time()

            # Nachlauf läuft
            if s["_post_rem"] > 0:
                s["_post"].append(chunk)
                s["_post_rem"] -= 1
                s["recording"] = True

                if s["_post_rem"] <= 0:
                    # Fertig → speichern
                    s["recording"] = False
                    pre   = list(s["_pre_snap"])
                    post  = list(s["_post"])
                    pk    = s["_evt_peak"]
                    th    = threshold
                    dur   = now - (s["_evt_start"] or now)
                    sr    = samplerate
                    name  = s["name"]
                    room  = s["room"]
                    s["_post"]     = []
                    s["_pre_snap"] = []
                    s["_evt_start"]= None
                    s["_evt_peak"] = 0.0

                    threading.Thread(
                        target=_save_event,
                        args=(pre, post, pk, th, dur, sr, name, room, sid),
                        daemon=True
                    ).start()

            elif db >= threshold:
                # Ereignis läuft
                if s["_evt_start"] is None:
                    s["_evt_start"] = now
                    s["_evt_peak"]  = db
                elif db > s["_evt_peak"]:
                    s["_evt_peak"] = db

            elif s["_evt_start"] is not None:
                # Ereignis gerade beendet
                if (now - s["_last_evt"]) > 3.0:
                    s["_post_rem"] = int(POST_SECS / 0.1)
                    s["_post"]     = []
                    s["_pre_snap"] = list(s["_ring"])
                    s["_last_evt"] = now
                else:
                    s["_evt_start"] = None
                    s["_evt_peak"]  = 0.0

    except Exception as e:
        with _lock:
            if sid in _sensors:
                _sensors[sid]["error"] = str(e)
        print(f"[Sensor] Audio-Fehler ({sid}): {e}")


def _rms_to_db(rms: float) -> float:
    if rms < 1e-9:
        return 0.0
    return max(0.0, 20 * np.log10(rms + 1e-9) + 90)


def _save_event(pre, post, db_level, threshold, duration, samplerate, name, room, sid):
    ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_file  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{ts_file}_{int(db_level)}dB_{room}.wav"

    # WAV speichern
    wav_file = ""
    try:
        path   = os.path.join(RECORDINGS_DIR, filename)
        frames = np.concatenate(pre + post, axis=0)
        data16 = (frames * 32767).astype(np.int16)
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(data16.tobytes())
        wav_file = filename
        _cleanup_old()
        print(f"[Sensor] Aufnahme gespeichert: {filename}")
    except Exception as e:
        print(f"[Sensor] WAV-Fehler: {e}")

    # DB-Eintrag
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO dog_events
            (timestamp, db_level, duration_s, threshold, wav_file, sensor_name, sensor_room)
            VALUES (?,?,?,?,?,?,?)
        """, (ts, round(db_level,1), round(duration,2), threshold, wav_file, name, room))
        conn.commit()
        conn.close()
        print(f"[Sensor] Ereignis geloggt: {ts}  {db_level:.1f} dB  {name}/{room}")
    except Exception as e:
        print(f"[Sensor] DB-Fehler: {e}")


def _cleanup_old():
    try:
        files = sorted([f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".wav")])
        while len(files) > MAX_FILES:
            os.remove(os.path.join(RECORDINGS_DIR, files.pop(0)))
    except Exception:
        pass


def get_recordings(limit=50):
    files = []
    if not os.path.exists(RECORDINGS_DIR):
        return files
    for f in sorted(os.listdir(RECORDINGS_DIR), reverse=True):
        if f.endswith(".wav"):
            path = os.path.join(RECORDINGS_DIR, f)
            size = os.path.getsize(path)
            files.append({
                "filename": f,
                "size_kb":  round(size / 1024, 1),
            })
    return files[:limit]


def delete_recording(filename: str) -> bool:
    path = os.path.join(RECORDINGS_DIR, os.path.basename(filename))
    if os.path.exists(path) and path.startswith(RECORDINGS_DIR):
        os.remove(path)
        return True
    return False
