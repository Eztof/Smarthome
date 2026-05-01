# ═══════════════════════════════════════════════════════════
#  modules/weather/fetcher.py  –  Open-Meteo API
# ═══════════════════════════════════════════════════════════

import requests
from datetime import datetime, timezone
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import config
from core.database import get_connection

# ── WMO-Codes ────────────────────────────────────────────
WMO = {
    0:  ("Klar",                 "☀️"),
    1:  ("Ueberwiegend klar",    "🌤️"),
    2:  ("Teilweise bewoelkt",   "⛅"),
    3:  ("Bedeckt",              "☁️"),
    45: ("Nebel",                "🌫️"),
    48: ("Raureif-Nebel",        "🌫️"),
    51: ("Leichter Nieselregen", "🌦️"),
    53: ("Nieselregen",          "🌦️"),
    55: ("Starker Nieselregen",  "🌧️"),
    61: ("Leichter Regen",       "🌧️"),
    63: ("Regen",                "🌧️"),
    65: ("Starker Regen",        "🌧️"),
    71: ("Leichter Schneefall",  "🌨️"),
    73: ("Schneefall",           "❄️"),
    75: ("Starker Schneefall",   "❄️"),
    77: ("Schneekoerner",        "🌨️"),
    80: ("Regenschauer",         "🌦️"),
    81: ("Starke Schauer",       "🌧️"),
    82: ("Heftige Schauer",      "⛈️"),
    85: ("Schneeschauer",        "🌨️"),
    86: ("Starke Schneeschauer", "❄️"),
    95: ("Gewitter",             "⛈️"),
    96: ("Gewitter+Hagel",       "⛈️"),
    99: ("Heftiger Hagel",       "⛈️"),
}

# Deutsche Beschreibungen (mit Umlauten für Anzeige)
WMO_DE = {
    0:  "Klar",              1:  "Überwiegend klar",
    2:  "Teilweise bewölkt", 3:  "Bedeckt",
    45: "Nebel",             48: "Raureif-Nebel",
    51: "Leichter Nieselregen", 53: "Nieselregen",
    55: "Starker Nieselregen",
    61: "Leichter Regen",    63: "Regen",
    65: "Starker Regen",
    71: "Leichter Schneefall", 73: "Schneefall",
    75: "Starker Schneefall", 77: "Schneekörner",
    80: "Regenschauer",      81: "Starke Schauer",
    82: "Heftige Schauer",
    85: "Schneeschauer",     86: "Starke Schneeschauer",
    95: "Gewitter",          96: "Gewitter mit Hagel",
    99: "Heftiger Hagel",
}


def wmo_info(code):
    desc  = WMO_DE.get(code, "Unbekannt")
    emoji = WMO.get(code, ("", "❓"))[1]
    return desc, emoji


def fetch_and_store():
    params = {
        "latitude":  config.LATITUDE,
        "longitude": config.LONGITUDE,
        "current": ["temperature_2m","apparent_temperature",
                    "relative_humidity_2m","wind_speed_10m",
                    "wind_direction_10m","weather_code","is_day"],
        "hourly":  ["temperature_2m","apparent_temperature",
                    "precipitation_probability","weather_code",
                    "relative_humidity_2m","wind_speed_10m"],
        "daily":   ["temperature_2m_max","temperature_2m_min",
                    "precipitation_sum","weather_code","sunrise","sunset"],
        "timezone":        "Europe/Berlin",
        "wind_speed_unit": "kmh",
        "forecast_days":   7,
    }
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params, timeout=10
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[Wetter] Fehler: {e}")
        return False

    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Lokale Zeit
    today = datetime.now().strftime("%Y-%m-%d")
    conn  = get_connection()
    cur   = conn.cursor()

    # Aktuell
    c    = data.get("current", {})
    code = c.get("weather_code", 0)
    desc, _ = wmo_info(code)
    cur.execute("""
        INSERT INTO weather_current
        (timestamp,temperature,feels_like,humidity,
         wind_speed,wind_direction,weather_code,description,is_day)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (now,
          c.get("temperature_2m"), c.get("apparent_temperature"),
          c.get("relative_humidity_2m"), c.get("wind_speed_10m"),
          c.get("wind_direction_10m"), code, desc, c.get("is_day",1)))

    # Stündlich – alle verfügbaren Tage speichern (heute + Prognose)
    h     = data.get("hourly", {})
    times = h.get("time", [])
    # Alle betroffenen Daten löschen und neu einfügen
    affected_dates = set(t[:10] for t in times)
    for d in affected_dates:
        cur.execute("DELETE FROM weather_hourly WHERE date=?", (d,))
    for i, t in enumerate(times):
        date_part = t[:10]
        hc   = h["weather_code"][i] if i < len(h.get("weather_code",[])) else 0
        hdesc, _ = wmo_info(hc)
        cur.execute("""
            INSERT INTO weather_hourly
            (date,hour_time,temperature,feels_like,humidity,
             wind_speed,precipitation_prob,weather_code,description)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (date_part, t[11:16],
              h["temperature_2m"][i]           if i < len(h.get("temperature_2m",[])) else None,
              h["apparent_temperature"][i]      if i < len(h.get("apparent_temperature",[])) else None,
              h["relative_humidity_2m"][i]      if i < len(h.get("relative_humidity_2m",[])) else None,
              h["wind_speed_10m"][i]            if i < len(h.get("wind_speed_10m",[])) else None,
              h["precipitation_probability"][i] if i < len(h.get("precipitation_probability",[])) else None,
              hc, hdesc))

    # Täglich
    d     = data.get("daily", {})
    for i, date in enumerate(d.get("time",[])):
        dc   = d["weather_code"][i] if i < len(d.get("weather_code",[])) else 0
        ddesc, _ = wmo_info(dc)
        cur.execute("""
            INSERT OR REPLACE INTO weather_daily
            (fetch_date,forecast_date,temp_max,temp_min,precipitation,
             weather_code,description,sunrise,sunset)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (today, date,
              d["temperature_2m_max"][i] if i < len(d.get("temperature_2m_max",[])) else None,
              d["temperature_2m_min"][i] if i < len(d.get("temperature_2m_min",[])) else None,
              d["precipitation_sum"][i]  if i < len(d.get("precipitation_sum",[])) else None,
              dc, ddesc,
              d["sunrise"][i] if i < len(d.get("sunrise",[])) else None,
              d["sunset"][i]  if i < len(d.get("sunset",[])) else None))

    conn.commit()
    conn.close()
    print(f"[Wetter] Aktualisiert: {now}")
    return True


def get_current():
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM weather_current ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    desc, emoji = wmo_info(r.get("weather_code", 0))
    r["emoji"] = emoji
    return r


def get_forecast():
    today   = datetime.now().strftime("%Y-%m-%d")
    days_de = ["Mo","Di","Mi","Do","Fr","Sa","So"]
    conn    = get_connection()
    rows    = conn.execute(
        "SELECT * FROM weather_daily WHERE fetch_date=? ORDER BY forecast_date ASC",
        (today,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        e = dict(row)
        desc, emoji = wmo_info(e.get("weather_code", 0))
        e["emoji"]       = emoji
        e["description"] = desc
        try:
            dt = datetime.strptime(e["forecast_date"], "%Y-%m-%d")
            e["weekday"]  = days_de[dt.weekday()]
            e["date_fmt"] = dt.strftime("%d.%m.")
            e["is_today"] = e["forecast_date"] == today
        except Exception:
            e["weekday"]  = ""
            e["date_fmt"] = e["forecast_date"]
            e["is_today"] = False
        result.append(e)
    return result


def get_hourly_today():
    today = datetime.now().strftime("%Y-%m-%d")
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT * FROM weather_hourly WHERE date=? ORDER BY hour_time ASC",
        (today,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history(limit=48):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM weather_current ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]
