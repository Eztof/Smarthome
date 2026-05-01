# ═══════════════════════════════════════════════════════════
#  web/routes.py  –  Alle Flask-Routen
# ═══════════════════════════════════════════════════════════

from flask import Blueprint, render_template, jsonify, request, Response
from datetime import datetime
import pytz, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from modules.weather  import fetcher   as weather
from modules.sensors  import manager   as sensors
from modules.thermopro import manager  as thermopro
from flask import send_file
from modules.hunde    import monitor   as hunde
from modules.media    import jellyfin  as media
from modules.appdb    import manager   as appdb

bp = Blueprint("main", __name__)
TZ = pytz.timezone(config.TIMEZONE)


def send_file_range(path, mimetype):
    """Sendet Mediendateien mit Range-Support (alles in RAM, Eventlet-kompatibel)."""
    import re
    file_size = os.path.getsize(path)
    range_header = request.headers.get("Range", None)

    # Gesamte Datei lesen (kein Generator – Eventlet verträgt kein Streaming)
    with open(path, "rb") as f:
        file_data = f.read()

    if range_header:
        m = re.search(r"bytes=([0-9]+)-([0-9]*)", range_header)
        if m:
            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else file_size - 1
            end   = min(end, file_size - 1)
            data  = file_data[start:end + 1]
            resp  = Response(data, status=206, mimetype=mimetype)
            resp.headers["Content-Range"]  = f"bytes {start}-{end}/{file_size}"
            resp.headers["Accept-Ranges"]  = "bytes"
            resp.headers["Content-Length"] = str(len(data))
            return resp

    resp = Response(file_data, status=200, mimetype=mimetype)
    resp.headers["Accept-Ranges"]  = "bytes"
    resp.headers["Content-Length"] = str(file_size)
    return resp


# ── Hilfsfunktionen ──────────────────────────────────────

def now_local():
    # Windows: datetime.now() nutzt die Windows-Systemzeit direkt
    # pytz nur für explizite Konvertierungen nötig
    return datetime.now(TZ)


def time_info():
    # Systemzeit direkt verwenden – korrekt wenn Windows-Zeitzone stimmt
    n = datetime.now()
    days   = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
    months = ["Januar","Februar","März","April","Mai","Juni",
              "Juli","August","September","Oktober","November","Dezember"]
    return {
        "weekday": days[n.weekday()],
        "day":     n.day,
        "month":   months[n.month-1],
        "year":    n.year,
        "time":    n.strftime("%H:%M"),
    }


@bp.app_template_global()
def db_badge_style(db):
    if db < 40:  return "background:rgba(79,195,247,0.15);color:#4fc3f7;"
    if db < 55:  return "background:rgba(105,219,124,0.15);color:#69db7c;"
    if db < 70:  return "background:rgba(255,179,71,0.15);color:#ffb347;"
    if db < 80:  return "background:rgba(230,74,25,0.15);color:#ff6b00;"
    return              "background:rgba(255,59,59,0.15);color:#ff3b3b;"


# ════════════════════════════════════════════════════════════
#  SEITEN
# ════════════════════════════════════════════════════════════

@bp.route("/")
def index():
    return render_template("index.html",
        weather  = weather.get_current(),
        forecast = weather.get_forecast()[:3],
        hunde    = hunde.get_state(),
        media    = media.get_status(),
        ti       = time_info(),
        location = config.LOCATION_NAME,
    )


@bp.route("/weather")
def weather_page():
    from datetime import datetime, timedelta
    n    = now_local()
    # Datum-Navigation: ?date=YYYY-MM-DD
    date_str  = request.args.get("date", n.strftime("%Y-%m-%d"))
    try:
        sel_date  = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        sel_date  = n.replace(tzinfo=None)

    today_str = n.strftime("%Y-%m-%d")
    is_today  = date_str == today_str

    # Vorheriger / nächster Tag
    prev_date = (sel_date - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date = (sel_date + timedelta(days=1)).strftime("%Y-%m-%d")

    # Maximales Datum: heute + Forecast-Tage
    max_date  = (n + timedelta(days=6)).strftime("%Y-%m-%d")
    # Minimales Datum: ältester Stundeneintrag in DB
    from core.database import get_connection as _gc
    _conn = _gc()
    _row  = _conn.execute("SELECT MIN(date) as d FROM weather_hourly").fetchone()
    _conn.close()
    min_date = (_row["d"] if _row and _row["d"] else today_str)

    # Stundendaten + Tagesprognose für gewählten Tag
    from core.database import get_connection as gc2
    conn2  = gc2()
    hourly = [dict(r) for r in conn2.execute(
        "SELECT * FROM weather_hourly WHERE date=? ORDER BY hour_time ASC", (date_str,)
    ).fetchall()]
    # Tageseintrag für gewähltes Datum (aus Prognose)
    day_entry = None
    for d in weather.get_forecast():
        if d.get("forecast_date") == date_str:
            day_entry = d
            break
    conn2.close()

    return render_template("weather.html",
        current    = weather.get_current() if is_today else None,
        day_entry  = day_entry,
        rain_top   = getattr(config, "WEATHER_RAIN_OPACITY_TOP", 0.55),
        rain_btm   = getattr(config, "WEATHER_RAIN_OPACITY_BTM", 0.08),
        rain_brd   = getattr(config, "WEATHER_RAIN_BORDER", 0.6),
        temp_fill  = getattr(config, "WEATHER_TEMP_OPACITY", 0.32),
        forecast   = weather.get_forecast(),
        hourly     = hourly,
        ti         = time_info(),
        location   = config.LOCATION_NAME,
        now_hour   = n.strftime("%H"),
        now_minute = n.minute,
        now_month  = n.month - 1,
        sel_date   = date_str,
        is_today   = is_today,
        prev_date  = prev_date,
        next_date  = next_date,
        min_date   = min_date,
        max_date   = max_date,
        sel_weekday= ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"][sel_date.weekday()],
        sel_datefmt= sel_date.strftime("%d. ") + ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"][sel_date.month-1],
    )


@bp.route("/hunde")
def hunde_page():
    return render_template("hunde.html",
        ti      = time_info(),
        state   = hunde.get_state(),
        events  = hunde.get_events(100),
        stats   = hunde.get_stats_today(),
        devices = hunde.get_devices(),
        daily   = hunde.get_daily_chart(7),
        hourly  = hunde.get_hourly_chart_today(),
    )


@bp.route("/media")
def media_page():
    return render_template("media.html",
        ti     = time_info(),
        status = media.get_status(),
        installed = media.is_installed(),
    )


@bp.route("/appdb")
def appdb_page():
    table    = request.args.get("table", "")
    page     = int(request.args.get("page", 1))
    per_page = 100
    offset   = (page - 1) * per_page

    tables   = appdb.get_tables()
    data     = {}
    if table:
        data = appdb.get_table_data(table, limit=per_page, offset=offset)

    return render_template("appdb.html",
        ti       = time_info(),
        tables   = tables,
        selected = table,
        data     = data,
        page     = page,
        per_page = per_page,
        db_info  = appdb.get_db_info(),
    )


# ════════════════════════════════════════════════════════════
#  APIs – Wetter
# ════════════════════════════════════════════════════════════

@bp.route("/api/weather/refresh", methods=["POST"])
def api_weather_refresh():
    return jsonify({"ok": weather.fetch_and_store()})

@bp.route("/api/weather/current")
def api_weather_current():
    return jsonify(weather.get_current() or {})


# ════════════════════════════════════════════════════════════
#  APIs – Hunde
# ════════════════════════════════════════════════════════════

@bp.route("/api/hunde/state")
def api_hunde_state():
    return jsonify(hunde.get_state())

@bp.route("/api/hunde/start",      methods=["POST"])
def api_hunde_start():
    hunde.start(); return jsonify({"ok": True})

@bp.route("/api/hunde/stop",       methods=["POST"])
def api_hunde_stop():
    hunde.stop();  return jsonify({"ok": True})

@bp.route("/api/hunde/threshold",  methods=["POST"])
def api_hunde_threshold():
    db = float(request.json.get("threshold", 65))
    hunde.set_threshold(db)
    return jsonify({"ok": True, "threshold": db})

@bp.route("/api/hunde/device",     methods=["POST"])
def api_hunde_device():
    idx = request.json.get("device_index")
    hunde.set_device(None if idx in (None, -1, "-1") else int(idx))
    return jsonify({"ok": True})

@bp.route("/api/hunde/reset_peak", methods=["POST"])
def api_hunde_reset_peak():
    hunde.reset_peak(); return jsonify({"ok": True})

@bp.route("/api/hunde/events")
def api_hunde_events():
    return jsonify(hunde.get_events(200))

@bp.route("/api/hunde/clear",      methods=["POST"])
def api_hunde_clear():
    hunde.clear_events(); return jsonify({"ok": True})

@bp.route("/api/hunde/charts")
def api_hunde_charts():
    return jsonify({
        "daily":  hunde.get_daily_chart(7),
        "hourly": hunde.get_hourly_chart_today(),
        "stats":  hunde.get_stats_today(),
        "all":    hunde.get_stats_all(),
    })


# ════════════════════════════════════════════════════════════
#  APIs – Media
# ════════════════════════════════════════════════════════════

@bp.route("/api/media/status")
def api_media_status():
    return jsonify(media.get_status())

@bp.route("/api/media/start",  methods=["POST"])
def api_media_start():
    return jsonify({"ok": media.start_service()})

@bp.route("/api/media/stop",   methods=["POST"])
def api_media_stop():
    return jsonify({"ok": media.stop_service()})


# ════════════════════════════════════════════════════════════
#  APIs – AppDB
# ════════════════════════════════════════════════════════════

@bp.route("/api/appdb/tables")
def api_appdb_tables():
    return jsonify(appdb.get_tables())

@bp.route("/api/appdb/data")
def api_appdb_data():
    table  = request.args.get("table", "")
    limit  = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    return jsonify(appdb.get_table_data(table, limit, offset))

@bp.route("/api/appdb/delete", methods=["POST"])
def api_appdb_delete():
    table = request.json.get("table")
    rid   = int(request.json.get("id"))
    return jsonify({"ok": appdb.delete_row(table, rid)})

@bp.route("/api/appdb/clear",  methods=["POST"])
def api_appdb_clear():
    table = request.json.get("table")
    return jsonify({"ok": appdb.clear_table(table)})

@bp.route("/api/appdb/export")
def api_appdb_export():
    table = request.args.get("table", "")
    csv   = appdb.export_csv(table)
    return Response(
        csv,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table}.csv"}
    )


# ════════════════════════════════════════════════════════════
#  APIs – Aufnahmen
# ════════════════════════════════════════════════════════════

@bp.route("/api/hunde/recordings")
def api_hunde_recordings():
    return jsonify(hunde.get_recordings())

@bp.route("/api/hunde/recordings/delete", methods=["POST"])
def api_hunde_recording_delete():
    fn = request.json.get("filename","")
    return jsonify({"ok": hunde.delete_recording(fn)})

@bp.route("/api/hunde/recordings/play/<filename>")
def api_hunde_recording_play(filename):
    from modules.hunde.monitor import RECORDINGS_DIR
    path = os.path.join(RECORDINGS_DIR, os.path.basename(filename))
    if os.path.exists(path):
        return send_file_range(path, "audio/wav")
    return jsonify({"error": "Datei nicht gefunden"}), 404

@bp.route("/hunde/aufnahmen")
def hunde_aufnahmen():
    return render_template("aufnahmen.html",
        ti=time_info(),
        recordings=sensors.get_recordings(),
    )


# ════════════════════════════════════════════════════════════
#  Sensor-Seite (Handy)
# ════════════════════════════════════════════════════════════

@bp.route("/sensor")
def sensor_page():
    return render_template("sensor.html",
        default_threshold=config.DOG_THRESHOLD_DB)


@bp.route("/api/sensors")
def api_sensors():
    return jsonify(sensors.get_all())

@bp.route("/api/sensors/recordings")
def api_sensors_recordings():
    return jsonify(sensors.get_recordings())

@bp.route("/api/sensors/recordings/delete", methods=["POST"])
def api_sensors_recording_delete():
    fn = request.json.get("filename","")
    return jsonify({"ok": sensors.delete_recording(fn)})

@bp.route("/api/sensors/recordings/play/<filename>")
def api_sensors_recording_play(filename):
    from modules.sensors.manager import RECORDINGS_DIR
    path = os.path.join(RECORDINGS_DIR, os.path.basename(filename))
    if not os.path.exists(path):
        return jsonify({"error": "Datei nicht gefunden"}), 404
    fn = os.path.basename(filename).lower()
    if fn.endswith(".webm"):
        mime = "video/webm"
    elif fn.endswith(".mp4"):
        mime = "video/mp4"
    else:
        mime = "audio/wav"
    return send_file_range(path, mime)


# ════════════════════════════════════════════════════════════
#  Zertifikat-Download (für Handy-Installation)
# ════════════════════════════════════════════════════════════

@bp.route("/cert")
def cert_page():
    return """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zertifikat installieren</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#0a0d12;color:#e8edf5;font-family:'Segoe UI',sans-serif;padding:24px;line-height:1.6;}
h1{color:#4fc3f7;font-size:22px;margin-bottom:8px;}
p{color:#5a6480;font-size:14px;margin-bottom:20px;}
.step{background:#161c28;border:1px solid #1e2535;border-radius:12px;padding:16px;margin-bottom:12px;}
.step-n{color:#4fc3f7;font-weight:700;font-size:13px;margin-bottom:6px;}
.step-t{font-size:15px;font-weight:600;margin-bottom:4px;}
.step-d{color:#5a6480;font-size:13px;}
.btn{display:block;background:#4fc3f7;color:#000;font-weight:700;font-size:16px;
     padding:16px;border-radius:12px;text-align:center;text-decoration:none;
     margin:20px 0;border:none;cursor:pointer;width:100%;}
.warn{background:rgba(255,179,71,0.1);border:1px solid rgba(255,179,71,0.3);
      border-radius:8px;padding:12px;color:#ffb347;font-size:13px;margin-bottom:16px;}
</style>
</head>
<body>
<h1>🔒 Zertifikat installieren</h1>
<p>Damit das Mikrofon über WLAN funktioniert, muss das Sicherheitszertifikat einmalig installiert werden.</p>

<div class="warn">⚠️ Nur im eigenen Heimnetz verwenden. Das Zertifikat gilt nur für diesen Server.</div>

<a href="/cert/download" class="btn">⬇ Zertifikat herunterladen</a>

<div class="step">
  <div class="step-n">Schritt 1</div>
  <div class="step-t">Zertifikat herunterladen</div>
  <div class="step-d">Auf den Button oben tippen. Die Datei <strong>pihome.crt</strong> wird heruntergeladen.</div>
</div>
<div class="step">
  <div class="step-n">Schritt 2 – Android</div>
  <div class="step-t">Einstellungen öffnen</div>
  <div class="step-d">Einstellungen → Sicherheit → Mehr Sicherheitseinstellungen → Zertifikate installieren → CA-Zertifikat → Trotzdem installieren → Datei auswählen</div>
</div>
<div class="step">
  <div class="step-n">Schritt 2 – iPhone</div>
  <div class="step-t">Profil installieren</div>
  <div class="step-d">Nach dem Download: Einstellungen → Allgemein → VPN & Geräteverwaltung → Profil installieren → Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen → aktivieren</div>
</div>
<div class="step">
  <div class="step-n">Schritt 3</div>
  <div class="step-t">Sensor öffnen</div>
  <div class="step-d">Zurück zu <a href="/sensor" style="color:#4fc3f7;">/sensor</a> — jetzt funktioniert das Mikrofon.</div>
</div>
</body>
</html>"""


@bp.route("/cert/download")
def cert_download():
    import os
    cert_path = os.path.join(os.path.dirname(config.__file__), "data", "cert.pem")
    if os.path.exists(cert_path):
        return send_file(
            cert_path,
            mimetype="application/x-x509-ca-cert",
            as_attachment=True,
            download_name="pihome.crt",
        )
    return "Kein Zertifikat gefunden.", 404


@bp.route("/api/sensors/upload_video", methods=["POST"])
def api_sensors_upload_video():
    from modules.sensors.manager import RECORDINGS_DIR
    from datetime import datetime

    video_file = request.files.get("video")
    room       = request.form.get("room", "Unbekannt").replace(" ", "_")
    name       = request.form.get("name", "Handy")

    if not video_file:
        return jsonify({"error": "Keine Videodatei"}), 400

    # Dateiendung aus MIME-Type oder Dateiname ermitteln
    mime = video_file.content_type or video_file.filename or ""
    if "mp4" in mime:
        ext = "mp4"
    else:
        ext = "webm"

    ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{ts}_video_{room}.{ext}"
    path     = os.path.join(RECORDINGS_DIR, filename)

    video_file.save(path)
    size_kb = round(os.path.getsize(path) / 1024, 1)
    print(f"[Video] Gespeichert: {filename} ({size_kb} KB) von {name}")

    return jsonify({"ok": True, "filename": filename, "size_kb": size_kb})


@bp.route("/api/media_port")
def api_media_port():
    """Gibt den Port des Medien-Dateiservers zurück."""
    return jsonify({"port": 5001})


# ════════════════════════════════════════════════════════════
#  ThermoPro TP357
# ════════════════════════════════════════════════════════════

@bp.route("/thermopro")
def thermopro_page():
    devices = thermopro.get_all_from_db()
    return render_template("thermopro.html", ti=time_info(), devices=devices)


@bp.route("/api/thermopro/devices")
def api_thermopro_devices():
    """Live-Geräteliste aus Cache (nur aktiv empfangene Geräte)."""
    live   = {d["mac"]: d for d in thermopro.get_all()}
    db_dev = thermopro.get_all_from_db()
    # Merge: DB-Geräte mit Live-Daten anreichern
    result = []
    for d in db_dev:
        if d["mac"] in live:
            result.append({**d, **live[d["mac"]], "online": True})
        else:
            result.append({**d, "online": False})
    # Neue Geräte die noch nicht in DB waren
    for mac, d in live.items():
        if not any(r["mac"] == mac for r in result):
            result.append({**d, "online": True})
    return jsonify(result)


@bp.route("/api/thermopro/history")
def api_thermopro_history():
    """Messverlauf für ein Gerät."""
    mac   = request.args.get("mac", "")
    hours = int(request.args.get("hours", 24))
    if not mac:
        return jsonify([])
    return jsonify(thermopro.get_history(mac, hours))


@bp.route("/api/thermopro/rename", methods=["POST"])
def api_thermopro_rename():
    """Setzt Raum und Anzeigename."""
    data = request.json or {}
    mac  = data.get("mac", "")
    room = data.get("room", "")
    name = data.get("name", "")
    if not mac:
        return jsonify({"ok": False, "error": "mac fehlt"})
    ok = thermopro.rename_device(mac, room, name)
    return jsonify({"ok": ok})

