#!/usr/bin/env python3
"""
weather.py - Mobile-friendly weather dashboard using Open-Meteo & Open-Meteo AQI.

Usage:
    python weather.py --lat 51.5 --lon -0.12 --host 0.0.0.0 --port 5000 --debug
"""

import argparse
import time
import threading
from datetime import datetime, timezone

import requests
from flask import Flask, render_template_string
from logzero import logger, loglevel
import logzero

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Open-Meteo weather dashboard")
    p.add_argument("--lat",   type=float, default=51.5074,  help="Latitude  (default: London)")
    p.add_argument("--lon",   type=float, default=-0.1278,  help="Longitude (default: London)")
    p.add_argument("--host",  default="0.0.0.0",            help="Flask host (default: 0.0.0.0)")
    p.add_argument("--port",  type=int, default=5000,        help="Flask port (default: 5000)")
    p.add_argument("--cache", type=int, default=900,         help="Cache TTL in seconds (default: 900)")
    p.add_argument("--debug", action="store_true",           help="Enable Flask debug + verbose logging")
    return p.parse_args()

# ---------------------------------------------------------------------------
# WMO weather-code → human label + emoji
# ---------------------------------------------------------------------------

WMO = {
    0:  ("Clear sky",              "☀️"),
    1:  ("Mainly clear",           "🌤️"),
    2:  ("Partly cloudy",          "⛅"),
    3:  ("Overcast",               "☁️"),
    45: ("Fog",                    "🌫️"),
    48: ("Icy fog",                "🌫️"),
    51: ("Light drizzle",          "🌦️"),
    53: ("Moderate drizzle",       "🌦️"),
    55: ("Dense drizzle",          "🌧️"),
    61: ("Slight rain",            "🌧️"),
    63: ("Moderate rain",          "🌧️"),
    65: ("Heavy rain",             "🌧️"),
    71: ("Slight snow",            "🌨️"),
    73: ("Moderate snow",          "❄️"),
    75: ("Heavy snow",             "❄️"),
    77: ("Snow grains",            "🌨️"),
    80: ("Slight showers",         "🌦️"),
    81: ("Moderate showers",       "🌧️"),
    82: ("Violent showers",        "⛈️"),
    85: ("Slight snow showers",    "🌨️"),
    86: ("Heavy snow showers",     "❄️"),
    95: ("Thunderstorm",           "⛈️"),
    96: ("Thunderstorm w/ hail",   "⛈️"),
    99: ("Thunderstorm w/ hail",   "⛈️"),
}

def wmo_label(code):
    info = WMO.get(int(code) if code is not None else 0, ("Unknown", "❓"))
    return {"label": info[0], "emoji": info[1]}

# ---------------------------------------------------------------------------
# Wind direction → compass
# ---------------------------------------------------------------------------

COMPASS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def deg_to_compass(deg):
    if deg is None:
        return "—"
    idx = round(float(deg) / 22.5) % 16
    return COMPASS[idx]

# ---------------------------------------------------------------------------
# AQI index label
# ---------------------------------------------------------------------------

def aqi_label(val):
    if val is None: return "—", ""
    v = int(val)
    if v <= 20:   return "Good",        "#4caf50"
    if v <= 40:   return "Fair",        "#8bc34a"
    if v <= 60:   return "Moderate",    "#ffeb3b"
    if v <= 80:   return "Poor",        "#ff9800"
    if v <= 100:  return "Very Poor",   "#f44336"
    return "Extremely Poor",            "#9c27b0"

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

BASE_WEATHER = "https://api.open-meteo.com/v1/forecast"
BASE_AQI     = "https://air-quality-api.open-meteo.com/v1/air-quality"

def fetch_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m", "relative_humidity_2m", "weather_code",
            "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
            "cloud_cover",
        ],
        "hourly": [
            "temperature_2m", "relative_humidity_2m", "weather_code",
            "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
            "cloud_cover",
        ],
        "daily": [
            "temperature_2m_max", "temperature_2m_min", "weather_code",
            "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant",
        ],
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 3,
    }
    r = requests.get(BASE_WEATHER, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_aqi(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["european_aqi"],
        "hourly": ["european_aqi"],
        "timezone": "auto",
        "forecast_days": 2,
    }
    r = requests.get(BASE_AQI, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

def process(weather_raw, aqi_raw):
    now_utc = datetime.now(timezone.utc)

    # ---- current ----------------------------------------------------------
    c = weather_raw["current"]
    aqi_cur = aqi_raw.get("current", {})
    wmo_cur = wmo_label(c.get("weather_code"))

    current = {
        "time":       c.get("time", ""),
        "temp":       c.get("temperature_2m"),
        "humidity":   c.get("relative_humidity_2m"),
        "wind":       c.get("wind_speed_10m"),
        "gusts":      c.get("wind_gusts_10m"),
        "wind_dir":   deg_to_compass(c.get("wind_direction_10m")),
        "wind_deg":   c.get("wind_direction_10m"),
        "cloud":      c.get("cloud_cover"),
        "weather":    wmo_cur,
        "aqi":        aqi_cur.get("european_aqi"),
        "aqi_label":  aqi_label(aqi_cur.get("european_aqi")),
    }

    # ---- daily ------------------------------------------------------------
    d = weather_raw.get("daily", {})
    days = []
    for i, date_str in enumerate(d.get("time", [])):
        days.append({
            "date":      date_str,
            "temp_max":  d["temperature_2m_max"][i],
            "temp_min":  d["temperature_2m_min"][i],
            "weather":   wmo_label(d["weather_code"][i]),
            "wind_max":  d["wind_speed_10m_max"][i],
            "gust_max":  d["wind_gusts_10m_max"][i],
            "wind_dir":  deg_to_compass(d["wind_direction_10m_dominant"][i]),
        })

    # ---- hourly (next 12 h) -----------------------------------------------
    h = weather_raw.get("hourly", {})
    ha = aqi_raw.get("hourly", {})
    times = h.get("time", [])

    # parse ISO times; API returns local time strings (tz=auto)
    hours = []
    found_now = False
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t)
        # make timezone-aware if needed
        if dt.tzinfo is None:
            # server gave naive local time; just compare string-wise hour
            pass
        if not found_now:
            # find first hour >= now (compare naively by index position heuristic)
            # Open-Meteo returns times in local tz; find first that is close to now
            now_str = now_utc.strftime("%Y-%m-%dT%H:00")
            if t >= now_str:
                found_now = True
        if found_now and len(hours) < 13:
            aqi_val = ha.get("european_aqi", [None]*len(times))[i] if i < len(ha.get("european_aqi",[])) else None
            hours.append({
                "time":     t[11:16],   # HH:MM
                "temp":     h["temperature_2m"][i],
                "humidity": h["relative_humidity_2m"][i],
                "wind":     h["wind_speed_10m"][i],
                "gusts":    h["wind_gusts_10m"][i],
                "wind_dir": deg_to_compass(h["wind_direction_10m"][i]),
                "cloud":    h["cloud_cover"][i],
                "weather":  wmo_label(h["weather_code"][i]),
                "aqi":      aqi_val,
                "aqi_label": aqi_label(aqi_val),
            })

    return {
        "current": current,
        "daily":   days,
        "hourly":  hours,
        "fetched_at": datetime.now().strftime("%H:%M:%S"),
        "timezone": weather_raw.get("timezone_abbreviation", ""),
    }

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class DataCache:
    def __init__(self, ttl, lat, lon):
        self.ttl   = ttl
        self.lat   = lat
        self.lon   = lon
        self._data = None
        self._ts   = 0
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            age = time.time() - self._ts
            if self._data is None or age >= self.ttl:
                logger.info("Cache miss – fetching Open-Meteo (age=%.0fs)", age)
                try:
                    weather_raw = fetch_weather(self.lat, self.lon)
                    aqi_raw     = fetch_aqi(self.lat, self.lon)
                    self._data  = process(weather_raw, aqi_raw)
                    self._ts    = time.time()
                    logger.info("Data fetched and cached successfully")
                except Exception as e:
                    logger.error("Fetch failed: %s", e)
                    if self._data is None:
                        raise
            else:
                logger.debug("Cache hit (age=%.0fs)", age)
            return self._data

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="theme-color" content="#0d1b2a">
<title>Weather</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Space+Grotesk:wght@300;400;600;700&display=swap');

  :root {
    --bg:        #0d1b2a;
    --surface:   #112233;
    --border:    #1e3a52;
    --accent:    #38bdf8;
    --accent2:   #f0abfc;
    --text:      #e2eaf4;
    --muted:     #7a99b8;
    --green:     #34d399;
    --yellow:    #fbbf24;
    --radius:    14px;
    --mono:      'DM Mono', monospace;
    --sans:      'Space Grotesk', sans-serif;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    min-height: 100vh;
    padding: 0 0 40px;
  }

  /* ---- header ---- */
  header {
    background: linear-gradient(160deg, #0a2540 0%, #0d1b2a 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 20px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 10;
    backdrop-filter: blur(8px);
  }
  header h1 {
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: .05em;
    color: var(--accent);
    text-transform: uppercase;
  }
  .updated {
    font-family: var(--mono);
    font-size: .72rem;
    color: var(--muted);
  }

  /* ---- sections ---- */
  main { padding: 16px 14px; display: flex; flex-direction: column; gap: 16px; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .section-title {
    font-size: .68rem;
    font-weight: 600;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 10px 14px 8px;
    border-bottom: 1px solid var(--border);
  }

  /* ---- current ---- */
  .current-top {
    padding: 20px 16px 12px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }
  .cur-weather { font-size: 3.6rem; line-height: 1; }
  .cur-right { text-align: right; }
  .cur-temp {
    font-size: 3.2rem;
    font-weight: 700;
    line-height: 1;
    color: var(--accent);
    font-family: var(--mono);
  }
  .cur-label { font-size: .95rem; color: var(--muted); margin-top: 4px; }
  .cur-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border-top: 1px solid var(--border);
  }
  .cur-cell {
    padding: 10px 14px;
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
  }
  .cur-cell:nth-child(even) { border-right: none; }
  .cur-cell:nth-last-child(-n+2) { border-bottom: none; }
  .cell-label { font-size: .65rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
  .cell-val { font-size: 1.05rem; font-family: var(--mono); font-weight: 500; margin-top: 2px; }
  .cell-sub { font-size: .72rem; color: var(--muted); margin-top: 1px; }

  /* wind arrow */
  .wind-arrow {
    display: inline-block;
    font-size: .9em;
    transition: transform .3s;
  }

  /* aqi pill */
  .aqi-pill {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 20px;
    font-size: .72rem;
    font-weight: 600;
    color: #000;
    margin-left: 5px;
    vertical-align: middle;
  }

  /* ---- daily ---- */
  .day-row {
    display: grid;
    grid-template-columns: 80px 1.6rem 1fr 70px;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-size: .88rem;
  }
  .day-row:last-child { border-bottom: none; }
  .day-name { font-weight: 600; }
  .day-emoji { text-align: center; font-size: 1.1rem; }
  .day-label { color: var(--muted); font-size: .78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .day-temps { font-family: var(--mono); text-align: right; font-size: .88rem; }
  .temp-max { color: var(--yellow); }
  .temp-min { color: var(--muted); font-size: .78rem; }
  .day-wind { color: var(--muted); font-size: .75rem; margin-top: 1px; }
  .day-detail { grid-column: 3 / 5; }

  /* ---- hourly ---- */
  .hourly-scroll {
    display: flex;
    overflow-x: auto;
    gap: 8px;
    padding: 12px 14px;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
    -webkit-overflow-scrolling: touch;
  }
  .hour-card {
    flex: 0 0 80px;
    background: #0d1b2a;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 6px;
    text-align: center;
    font-family: var(--mono);
  }
  .hour-time { font-size: .7rem; color: var(--muted); margin-bottom: 4px; }
  .hour-emoji { font-size: 1.4rem; margin: 2px 0; }
  .hour-temp { font-size: 1rem; font-weight: 500; color: var(--accent); }
  .hour-wind { font-size: .68rem; color: var(--muted); margin-top: 3px; }
  .hour-cloud { font-size: .68rem; color: var(--muted); }
  .hour-hum { font-size: .68rem; color: var(--accent2); }

  /* current hour highlight */
  .hour-card.now {
    border-color: var(--accent);
    background: #0e2236;
  }
  .hour-card.now .hour-time { color: var(--accent); font-weight: 500; }

  /* ---- cloud bar ---- */
  .bar-track {
    height: 5px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    margin-top: 4px;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    border-radius: 3px;
  }

  /* ---- footer ---- */
  .coord-bar {
    font-family: var(--mono);
    font-size: .68rem;
    color: var(--muted);
    text-align: center;
    padding-top: 4px;
  }
</style>
</head>
<body>

<header>
  <h1>⛅ Weather</h1>
  <span class="updated">Updated {{ data.fetched_at }} {{ data.timezone }}</span>
</header>

<main>

  {# ---- CURRENT ---- #}
  {% set c = data.current %}
  <div class="card">
    <div class="section-title">Current Conditions</div>
    <div class="current-top">
      <div class="cur-weather">{{ c.weather.emoji }}</div>
      <div class="cur-right">
        <div class="cur-temp">{{ c.temp | round(1) }}°</div>
        <div class="cur-label">{{ c.weather.label }}</div>
      </div>
    </div>
    <div class="cur-grid">
      <div class="cur-cell">
        <div class="cell-label">Wind</div>
        <div class="cell-val">{{ c.wind | round(1) }} mph</div>
        <div class="cell-sub">Gusts {{ c.gusts | round(1) }} mph</div>
      </div>
      <div class="cur-cell">
        <div class="cell-label">Direction</div>
        <div class="cell-val">{{ c.wind_dir }}
          <span class="wind-arrow" style="transform:rotate({{ c.wind_deg }}deg)">↑</span>
        </div>
        <div class="cell-sub">{{ c.wind_deg }}°</div>
      </div>
      <div class="cur-cell">
        <div class="cell-label">Humidity</div>
        <div class="cell-val">{{ c.humidity }}%</div>
        <div class="bar-track"><div class="bar-fill" style="width:{{ c.humidity }}%"></div></div>
      </div>
      <div class="cur-cell">
        <div class="cell-label">Cloud Cover</div>
        <div class="cell-val">{{ c.cloud }}%</div>
        <div class="bar-track"><div class="bar-fill" style="width:{{ c.cloud }}%"></div></div>
      </div>
      <div class="cur-cell" style="grid-column:1/-1; border-right:none;">
        <div class="cell-label">Air Quality (EU AQI)</div>
        <div class="cell-val">
          {% if c.aqi is not none %}
            {{ c.aqi }}
            <span class="aqi-pill" style="background:{{ c.aqi_label[1] }}">{{ c.aqi_label[0] }}</span>
          {% else %}—{% endif %}
        </div>
      </div>
    </div>
  </div>

  {# ---- DAILY ---- #}
  <div class="card">
    <div class="section-title">Daily Forecast</div>
    {% for day in data.daily %}
    {% set dow = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] %}
    {% set dt = day.date %}
    <div class="day-row">
      <div>
        <div class="day-name">
          {% if loop.index0 == 0 %}Today
          {% elif loop.index0 == 1 %}Tomorrow
          {% else %}{{ dt }}{% endif %}
        </div>
        <div class="day-wind">{{ day.wind_dir }} {{ day.wind_max | round(0) | int }}↑{{ day.gust_max | round(0) | int }} mph</div>
      </div>
      <div class="day-emoji">{{ day.weather.emoji }}</div>
      <div class="day-label">{{ day.weather.label }}</div>
      <div class="day-temps">
        <div class="temp-max">{{ day.temp_max | round(1) }}°</div>
        <div class="temp-min">{{ day.temp_min | round(1) }}°</div>
      </div>
    </div>
    {% endfor %}
  </div>

  {# ---- HOURLY ---- #}
  <div class="card">
    <div class="section-title">Next 12 Hours</div>
    <div class="hourly-scroll">
      {% for h in data.hourly %}
      <div class="hour-card {% if loop.index0 == 0 %}now{% endif %}">
        <div class="hour-time">{% if loop.index0 == 0 %}Now{% else %}{{ h.time }}{% endif %}</div>
        <div class="hour-emoji">{{ h.weather.emoji }}</div>
        <div class="hour-temp">{{ h.temp | round(1) }}°</div>
        <div class="hour-wind">{{ h.wind_dir }} {{ h.wind | round(0) | int }}mph</div>
        <div class="hour-cloud">☁ {{ h.cloud }}%</div>
        <div class="hour-hum">💧{{ h.humidity }}%</div>
      </div>
      {% endfor %}
    </div>
  </div>

  <div class="coord-bar">{{ lat }}°N {{ lon }}°E · cache {{ cache_ttl }}s · Open-Meteo</div>

</main>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
_cache: DataCache = None
_args  = None

@app.route("/")
def index():
    data = _cache.get()
    return render_template_string(
        TEMPLATE,
        data=data,
        lat=_args.lat,
        lon=_args.lon,
        cache_ttl=_args.cache,
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global _cache, _args
    _args = parse_args()

    if _args.debug:
        loglevel(10)   # DEBUG
    else:
        loglevel(20)   # INFO

    logzero.formatter(logzero.LogFormatter(fmt="%(asctime)s %(levelname)s %(message)s"))

    logger.info("Starting weather server at http://%s:%d/", _args.host, _args.port)
    logger.info("Location: lat=%.4f lon=%.4f  cache TTL=%ds", _args.lat, _args.lon, _args.cache)

    _cache = DataCache(ttl=_args.cache, lat=_args.lat, lon=_args.lon)

    # pre-warm cache so first request is instant
    try:
        _cache.get()
    except Exception as e:
        logger.warning("Pre-warm failed (%s) – will retry on first request", e)

    app.run(host=_args.host, port=_args.port, debug=_args.debug)

if __name__ == "__main__":
    main()
