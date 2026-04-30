# ═══════════════════════════════════════════════════════════
#  main.py  –  Smarthome Einstiegspunkt (mit SocketIO)
# ═══════════════════════════════════════════════════════════

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_socketio import SocketIO, emit, disconnect
import config
from core.database import init_db
from core import scheduler
from modules.weather import fetcher as weather
from modules.sensors import manager as sensors
from web.routes import bp

# ── Flask + SocketIO ─────────────────────────────────────
app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
)
app.config["SECRET_KEY"] = "pihome-secret-2024"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

app.register_blueprint(bp)

# ── SocketIO Events ──────────────────────────────────────

@socketio.on("connect")
def on_connect():
    print(f"[WS] Verbindung: {request_sid()}")


@socketio.on("disconnect")
def on_disconnect():
    sensors.unregister(request_sid())
    # Allen Clients aktualisierten Status senden
    socketio.emit("sensors_update", sensors.get_all())


@socketio.on("sensor_register")
def on_sensor_register(data):
    sid       = request_sid()
    name      = data.get("name", "Handy")
    room      = data.get("room", "Unbekannt")
    threshold = float(data.get("threshold", config.DOG_THRESHOLD_DB))
    sensors.register(sid, name, room, threshold)
    emit("registered", {"ok": True, "sid": sid})
    socketio.emit("sensors_update", sensors.get_all())


@socketio.on("audio_chunk")
def on_audio_chunk(data):
    sid        = request_sid()
    audio_b64  = data.get("audio", "")
    samplerate = int(data.get("samplerate", 16000))
    sensors.process_audio_chunk(sid, audio_b64, samplerate)
    # dB-Update an alle Dashboard-Clients
    socketio.emit("sensor_db_update", {
        "sid": sid,
        "db":  sensors.get_all()
    })


@socketio.on("sensor_threshold")
def on_sensor_threshold(data):
    sid       = request_sid()
    threshold = float(data.get("threshold", 65))
    sensors.set_threshold(sid, threshold)
    emit("threshold_updated", {"threshold": threshold})


@socketio.on("sensor_reset_peak")
def on_reset_peak():
    sensors.reset_peak(request_sid())


def request_sid():
    from flask import request
    return request.sid


# ── Socketio-Instanz für routes verfügbar machen ─────────
app.socketio = socketio


# ── Start ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== PI-HOME Smarthome (mit WebSocket) ===")

    init_db()

    print("[Start] Wetterdaten werden abgerufen...")
    weather.fetch_and_store()

    scheduler.start()

    print(f"Laeuft auf: http://localhost:{config.PORT}")
    print(f"Im Netzwerk: http://<IP>:{config.PORT}")
    print(f"Handy-Sensor: http://<IP>:{config.PORT}/sensor")
    print("=========================================\n")

    # SSL-Zertifikat erstellen falls noch nicht vorhanden
    cert_file = os.path.join(os.path.dirname(__file__), "data", "cert.pem")
    key_file  = os.path.join(os.path.dirname(__file__), "data", "key.pem")

    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        print("[SSL] Erstelle selbst-signiertes Zertifikat...")
        try:
            from OpenSSL import crypto
            k = crypto.PKey()
            k.generate_key(crypto.TYPE_RSA, 2048)
            cert = crypto.X509()
            cert.get_subject().CN = "pihome.local"
            cert.set_serial_number(1)
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(10*365*24*60*60)  # 10 Jahre
            cert.set_issuer(cert.get_subject())
            cert.set_pubkey(k)
            cert.sign(k, "sha256")
            with open(cert_file, "wb") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
            with open(key_file, "wb") as f:
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
            print("[SSL] Zertifikat erstellt.")
        except Exception as e:
            print(f"[SSL] Fehler: {e} — starte ohne SSL")
            cert_file = None
            key_file  = None

    ssl_ctx = None
    if cert_file and key_file:
        import ssl
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert_file, key_file)
        print(f"Laeuft auf: https://localhost:{config.PORT}")
        print(f"Im Netzwerk: https://<IP>:{config.PORT}")
        print(f"Handy-Sensor: https://<IP>:{config.PORT}/sensor")
    else:
        print(f"Laeuft auf: http://localhost:{config.PORT}")

    print("=========================================\n")

    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
        ssl_context=ssl_ctx,
    )
