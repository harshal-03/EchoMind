"""The ONLY actions the orchestrator will ever run. Anything else is blocked."""
import json
import urllib.parse
import urllib.request

import netlog
from config import ONLINE_ALLOWLIST

ALLOWED_TOOLS = {"remember_note", "search_notes", "get_weather", "web_lookup", "privacy_report",
                 "add_task", "list_tasks", "complete_task", "set_reminder", "summarize", "create_calendar_event", "list_upcoming_events",
                 "mail_digest", "github_overview", "github_repo",
                 "search_docs", "docs_status"}

WMO = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy",
       48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
       61: "light rain", 63: "rain", 65: "heavy rain", 80: "rain showers",
       81: "rain showers", 82: "violent showers", 95: "thunderstorm"}


def _http_get_json(url):
    host = urllib.parse.urlparse(url).hostname
    if host not in ONLINE_ALLOWLIST:               # hard allowlist
        raise PermissionError(f"Host not allowlisted: {host}")
    netlog.record(host, "external")
    req = urllib.request.Request(url, headers={"User-Agent": "EchoMind/1.0 (makethon project)"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)


def get_weather(city):
    geo = _http_get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&name="
                         + urllib.parse.quote(city))
    results = geo.get("results")
    if not results:
        return f"I couldn't find a place called {city}."
    place = results[0]
    w = _http_get_json(
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={place['latitude']}&longitude={place['longitude']}"
        "&current=temperature_2m,wind_speed_10m,weather_code")
    cur = w["current"]
    desc = WMO.get(cur.get("weather_code"), "mixed conditions")
    return (f"In {place['name']} it's {cur['temperature_2m']}°C with {desc} "
            f"and wind at {cur['wind_speed_10m']} km/h.")


def web_lookup(query):
    """Online fact lookup. Only the short keyword query leaves the device."""
    s = _http_get_json("https://en.wikipedia.org/w/api.php?action=query&list=search"
                       "&format=json&srlimit=1&srsearch=" + urllib.parse.quote(query))
    hits = s.get("query", {}).get("search", [])
    if not hits:
        return ""
    title = hits[0]["title"]
    d = _http_get_json("https://en.wikipedia.org/api/rest_v1/page/summary/"
                       + urllib.parse.quote(title.replace(" ", "_")))
    return f"{title}: {d.get('extract', '')[:600]}"
