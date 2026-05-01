# ═══════════════════════════════════════════════════════════
#  main.py  –  Smarthome Einstiegspunkt
#  WICHTIG: eventlet.monkey_patch() muss als allererstes!
# ═══════════════════════════════════════════════════════════

# ── 1. Eventlet patchen BEVOR alles andere importiert wird ─
import eventlet
eventlet.monkey_patch()

# ── 2. Erst jetzt alle anderen Imports ────────────────────
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_socketio import SocketIO, emit
import config
from core.database import init_db
from core import scheduler
from modules.weather    import fetcher  as weather
from modules.sensors    import manager  as sensors
from web.routes import bp

# ── Flask + SocketIO ─────────────────────────────────────
app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
)
app.config["SECRET_KEY"]         = "pihome-secret-2024"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB Upload-Limit

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet",
    logger=False,
    engineio_logger=False,
)

app.register_blueprint(bp)
app.socketio = socketio


# ── SocketIO Events ──────────────────────────────────────

def get_sid():
    from flask import request
    return request.sid


@socketio.on("connect")
def on_connect():
    print(f"[WS] Verbunden: {get_sid()}")


@socketio.on("disconnect")
def on_disconnect():
    sensors.unregister(get_sid())
    socketio.emit("sensors_update", sensors.get_all())


@socketio.on("sensor_register")
def on_sensor_register(data):
    sid       = get_sid()
    name      = data.get("name", "Handy")
    room      = data.get("room", "Unbekannt")
    threshold = float(data.get("threshold", config.DOG_THRESHOLD_DB))
    sensors.register(sid, name, room, threshold, data)
    emit("registered", {"ok": True, "sid": sid})
    socketio.emit("sensors_update", sensors.get_all())


@socketio.on("audio_chunk")
def on_audio_chunk(data):
    sid        = get_sid()
    audio_b64  = data.get("audio", "")
    samplerate = int(data.get("samplerate", 16000))
    sensors.process_audio_chunk(sid, audio_b64, samplerate)
    socketio.emit("sensor_db_update", {"sid": sid, "db": sensors.get_all()})


@socketio.on("sensor_threshold")
def on_sensor_threshold(data):
    sensors.set_threshold(get_sid(), float(data.get("threshold", 65)))
    emit("threshold_updated", {"threshold": data.get("threshold")})


@socketio.on("sensor_reset_peak")
def on_reset_peak():
    sensors.reset_peak(get_sid())


# ── Medien-Dateiserver (Port 5001, separater Prozess) ─────
MEDIA_PORT = 5001

def start_media_server():
    import subprocess as _sp
    from modules.sensors.manager import RECORDINGS_DIR
    script = os.path.join(os.path.dirname(__file__), "media_server.py")
    _sp.Popen(
        [sys.executable, script, RECORDINGS_DIR, str(MEDIA_PORT)],
        creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
    )
    print(f"[Media] Dateiserver gestartet auf Port {MEDIA_PORT}")


def start_thermopro_scanner():
    import subprocess as _sp
    script = os.path.join(os.path.dirname(__file__), "thermopro_scanner.py")
    if not os.path.exists(script):
        print("[ThermoPro] thermopro_scanner.py nicht gefunden – Scanner deaktiviert")
        return
    _sp.Popen(
        [sys.executable, script],
        creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
    )
    print("[ThermoPro] BLE-Scanner-Prozess gestartet")


# ── Start ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== PI-HOME Smarthome ===")

    init_db()

    print("[Start] Wetterdaten werden abgerufen...")
    weather.fetch_and_store()

    scheduler.start()
    start_media_server()
    start_thermopro_scanner()

    print(f"Laeuft auf:   http://localhost:{config.PORT}")
    print(f"Netzwerk:     http://192.168.178.104:{config.PORT}")
    print(f"Handy-Sensor: http://192.168.178.104:{config.PORT}/sensor")
    print("=========================================\n")

    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
    )
