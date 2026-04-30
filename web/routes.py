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
from flask import send_file
from modules.hunde    import monitor   as hunde
from modules.media    import jellyfin  as media
from modules.appdb    import manager   as appdb

bp = Blueprint("main", __name__)
TZ = pytz.timezone(config.TIMEZONE)


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
    n = now_local()
    return render_template("weather.html",
        current   = weather.get_current(),
        forecast  = weather.get_forecast(),
        hourly    = weather.get_hourly_today(),
        ti        = time_info(),
        location  = config.LOCATION_NAME,
        now_hour  = n.strftime("%H"),
        now_minute= n.minute,
        now_month = n.month - 1,
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
    import os
    from modules.hunde.monitor import RECORDINGS_DIR
    path = os.path.join(RECORDINGS_DIR, os.path.basename(filename))
    if os.path.exists(path):
        return send_file(path, mimetype="audio/wav")
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
    if os.path.exists(path):
        return send_file(path, mimetype="audio/wav")
    return jsonify({"error": "Datei nicht gefunden"}), 404


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
