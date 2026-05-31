# weather.py — Open-Meteo mobile weather dashboard

A single-file Flask app that pulls weather + air quality from
[Open-Meteo](https://open-meteo.com/) (free, no API key needed) and serves
a clean, phone-friendly dark dashboard.

## What it shows

| Panel | Data |
|-------|------|
| **Current** | Weather type & emoji, temperature, wind speed, gusts, direction (compass + degrees), humidity, cloud cover, EU Air Quality Index |
| **Daily** (3 days) | Hi/lo temps, prevailing weather, max wind + gusts, dominant wind direction |
| **Hourly** (next 12 h) | Weather emoji, temp, wind, cloud cover, humidity — horizontally scrollable |

## Requirements

```
pip install -r requirements.txt
```

## Usage

```bash
# London (default)
python weather.py

# Custom location, port, verbose
python weather.py --lat 40.7128 --lon -74.0060 --port 8080 --debug

# Raspberry Pi / LAN server
python weather.py --lat 48.8566 --lon 2.3522 --host 0.0.0.0 --port 5000
```

## All options

| Flag | Default | Description |
|------|---------|-------------|
| `--lat` | 51.5074 | Latitude |
| `--lon` | -0.1278 | Longitude |
| `--host` | 0.0.0.0 | Bind host |
| `--port` | 5000 | Bind port |
| `--cache` | 900 | Cache TTL in seconds (15 min) |
| `--debug` | off | Flask debug mode + verbose logging |

## Caching

Open-Meteo is queried **at most once per `--cache` seconds** (default 15 min).
All requests between refreshes are served instantly from memory.
The cache is thread-safe and pre-warmed at startup.

## Data sources

- Weather & forecast: `api.open-meteo.com` (WMO weather codes)
- Air quality: `air-quality-api.open-meteo.com` (EU AQI)

Both are free and require no API key.
