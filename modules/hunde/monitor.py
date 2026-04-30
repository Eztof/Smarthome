# ═══════════════════════════════════════════════════════════
#  modules/hunde/monitor.py  –  Mikrofon-Überwachung
#  Mit Ringpuffer-Aufnahme: X Sek. vor/nach Ereignis
# ═══════════════════════════════════════════════════════════

import threading
import time
import numpy as np
import wave
import os
from collections import deque
from datetime import datetime
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import config
from core.database import get_connection, get_setting, set_setting

# ── Aufnahme-Ordner ──────────────────────────────────────
RECORDINGS_DIR = os.path.join(os.path.dirname(config.DB_PATH), "aufnahmen")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# ── Einstellungen ─────────────────────────────────────────
PRE_SECS  = 10    # Sekunden VOR dem Ereignis
POST_SECS = 10    # Sekunden NACH dem Ereignis
MAX_FILES = 100   # Maximale Anzahl gespeicherter Aufnahmen

# ── Gemeinsamer State ─────────────────────────────────────
_lock  = threading.Lock()
_state = {
    "running":    False,
    "current_db": 0.0,
    "peak_db":    0.0,
    "threshold":  float(config.DOG_THRESHOLD_DB),
    "device":     None,
    "error":      None,
    "recording":  False,   # Gerade wird Nachlauf aufgenommen
}
_thread = None


# ── Öffentliche API ───────────────────────────────────────

def get_state():
    with _lock:
        return {
            "running":    _state["running"],
            "current_db": round(_state["current_db"], 1),
            "peak_db":    round(_state["peak_db"], 1),
            "threshold":  _state["threshold"],
            "error":      _state["error"],
            "recording":  _state["recording"],
        }


def set_threshold(db: float):
    with _lock:
        _state["threshold"] = float(db)
    set_setting("dog_threshold", str(db))


def set_device(index):
    with _lock:
        _state["device"] = index


def get_devices():
    try:
        import sounddevice as sd
        result = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                result.append({
                    "index": i,
                    "name":  d["name"],
                    "sr":    int(d["default_samplerate"]),
                })
        return result
    except Exception as e:
        return [{"index": -1, "name": f"Fehler: {e}", "sr": 44100}]


def start():
    global _thread
    with _lock:
        if _state["running"]:
            return
        saved = get_setting("dog_threshold")
        if saved:
            _state["threshold"] = float(saved)
        _state["running"]    = True
        _state["peak_db"]    = 0.0
        _state["error"]      = None
        _state["current_db"] = 0.0
        _state["recording"]  = False
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    print("[Hunde] Monitor gestartet.")


def stop():
    with _lock:
        _state["running"] = False
    print("[Hunde] Monitor gestoppt.")


def reset_peak():
    with _lock:
        _state["peak_db"] = 0.0


def get_events(limit=200):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM dog_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats_today():
    today = datetime.now().strftime("%Y-%m-%d")
    conn  = get_connection()
    row   = conn.execute("""
        SELECT COUNT(*) as total,
               MAX(db_level) as max_db,
               AVG(db_level) as avg_db
        FROM dog_events WHERE timestamp LIKE ?
    """, (today + "%",)).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_stats_all():
    conn = get_connection()
    row  = conn.execute("""
        SELECT COUNT(*) as total,
               MAX(db_level) as max_db,
               AVG(db_level) as avg_db
        FROM dog_events
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_daily_chart(days=7):
    conn = get_connection()
    rows = conn.execute("""
        SELECT substr(timestamp,1,10) as day, COUNT(*) as count
        FROM dog_events GROUP BY day ORDER BY day DESC LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_hourly_chart_today():
    today = datetime.now().strftime("%Y-%m-%d")
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT substr(timestamp,12,2) as hour, COUNT(*) as count
        FROM dog_events WHERE timestamp LIKE ?
        GROUP BY hour ORDER BY hour ASC
    """, (today + "%",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recordings(limit=50):
    """Gibt gespeicherte Aufnahmen sortiert nach Datum zurück."""
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
                "timestamp": f[:19].replace("_", " ").replace("-", "-"),
            })
    return files[:limit]


def delete_recording(filename: str) -> bool:
    path = os.path.join(RECORDINGS_DIR, os.path.basename(filename))
    if os.path.exists(path) and path.startswith(RECORDINGS_DIR):
        os.remove(path)
        return True
    return False


def clear_events():
    conn = get_connection()
    conn.execute("DELETE FROM dog_events")
    conn.commit()
    conn.close()


# ── Interne Logik ─────────────────────────────────────────

def _rms_to_db(rms: float) -> float:
    if rms < 1e-9:
        return 0.0
    return max(0.0, 20 * np.log10(rms + 1e-9) + 90)


def _log_event(db_level: float, threshold: float, duration: float, wav_file: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    conn.execute(
        "INSERT INTO dog_events (timestamp,db_level,duration_s,threshold,wav_file) VALUES (?,?,?,?,?)",
        (ts, round(db_level, 1), round(duration, 2), threshold, wav_file)
    )
    conn.commit()
    conn.close()
    print(f"[Hunde] Ereignis: {ts}  {db_level:.1f} dB  ({duration:.1f}s)  → {wav_file}")


def _save_wav(frames: list, samplerate: int, filename: str):
    """Speichert eine Liste von float32-Arrays als WAV-Datei."""
    path = os.path.join(RECORDINGS_DIR, filename)
    try:
        data = np.concatenate(frames, axis=0)
        # float32 → int16 konvertieren
        data_int16 = (data * 32767).astype(np.int16)
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)          # 2 Bytes = int16
            wf.setframerate(samplerate)
            wf.writeframes(data_int16.tobytes())
        print(f"[Hunde] WAV gespeichert: {filename}")
        _cleanup_old_recordings()
        return filename
    except Exception as e:
        print(f"[Hunde] WAV-Fehler: {e}")
        return ""


def _cleanup_old_recordings():
    """Löscht älteste Aufnahmen wenn MAX_FILES überschritten."""
    try:
        files = sorted([
            f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".wav")
        ])
        while len(files) > MAX_FILES:
            os.remove(os.path.join(RECORDINGS_DIR, files.pop(0)))
    except Exception:
        pass


def _loop():
    try:
        import sounddevice as sd
    except Exception as e:
        with _lock:
            _state["error"]   = f"sounddevice nicht verfuegbar: {e}"
            _state["running"] = False
        return

    with _lock:
        device = _state["device"]

    # Samplerate ermitteln
    samplerate = config.DOG_SAMPLERATE
    try:
        info = sd.query_devices(device if device is not None else sd.default.device[0])
        samplerate = int(info["default_samplerate"])
    except Exception:
        pass

    chunk        = int(samplerate * config.DOG_CHUNK_DURATION)
    pre_chunks   = int(PRE_SECS  / config.DOG_CHUNK_DURATION)
    post_chunks  = int(POST_SECS / config.DOG_CHUNK_DURATION)
    cooldown     = config.DOG_COOLDOWN

    # Ringpuffer: hält immer die letzten PRE_SECS Sekunden
    ring_buffer = deque(maxlen=pre_chunks)

    last_event_time  = 0.0
    event_start_time = None
    event_peak_db    = 0.0
    post_buffer      = []     # Chunks für Nachlauf
    post_remaining   = 0      # Noch aufzunehmende Nachlauf-Chunks
    event_pre_snap   = []     # Snapshot des Ringpuffers beim Auslösen
    is_post_recording= False

    try:
        with sd.InputStream(
            device=device,
            channels=1,
            samplerate=samplerate,
            blocksize=chunk,
            dtype="float32",
        ) as stream:
            with _lock:
                _state["error"] = None
            print(f"[Hunde] Mikrofon aktiv ({samplerate} Hz). Ringpuffer: {PRE_SECS}s vor / {POST_SECS}s nach Ereignis.")

            while True:
                with _lock:
                    if not _state["running"]:
                        break
                    threshold = _state["threshold"]

                data, _ = stream.read(chunk)
                chunk_copy = data.copy()

                rms = float(np.sqrt(np.mean(data ** 2)))
                db  = _rms_to_db(rms)

                with _lock:
                    _state["current_db"] = db
                    if db > _state["peak_db"]:
                        _state["peak_db"] = db

                now = time.time()

                # Ringpuffer füllen (immer)
                ring_buffer.append(chunk_copy)

                # ── Nachlauf-Aufnahme läuft ───────────────
                if is_post_recording:
                    post_buffer.append(chunk_copy)
                    post_remaining -= 1
                    with _lock:
                        _state["recording"] = True

                    if post_remaining <= 0:
                        # Nachlauf fertig → WAV speichern
                        is_post_recording = False
                        with _lock:
                            _state["recording"] = False

                        duration = now - event_start_time
                        ts_str   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        filename = f"{ts_str}_{int(event_peak_db)}dB.wav"

                        all_frames = list(event_pre_snap) + post_buffer
                        threading.Thread(
                            target=lambda f=all_frames, sr=samplerate, fn=filename,
                                          pk=event_peak_db, th=threshold, dur=duration:
                                _log_event(pk, th, dur, _save_wav(f, sr, fn)),
                            daemon=True
                        ).start()

                        post_buffer   = []
                        event_pre_snap= []
                        event_start_time = None
                        event_peak_db = 0.0

                # ── Schwelle überschritten? ───────────────
                elif db >= threshold:
                    if event_start_time is None:
                        event_start_time = now
                        event_peak_db    = db
                    else:
                        if db > event_peak_db:
                            event_peak_db = db

                # ── Ereignis gerade beendet? ──────────────
                elif event_start_time is not None:
                    if (now - last_event_time) > cooldown:
                        # Nachlauf starten
                        is_post_recording = True
                        post_remaining    = post_chunks
                        post_buffer       = []
                        event_pre_snap    = list(ring_buffer)
                        last_event_time   = now
                    else:
                        # Cooldown noch aktiv → Ereignis verwerfen
                        event_start_time = None
                        event_peak_db    = 0.0

    except Exception as e:
        with _lock:
            _state["error"]      = str(e)
            _state["running"]    = False
            _state["current_db"] = 0.0
            _state["recording"]  = False
        print(f"[Hunde] Fehler: {e}")
