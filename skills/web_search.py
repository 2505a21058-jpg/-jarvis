import requests
from urllib.parse import quote, urlencode

from config import JARVIS_USER_AGENT, OPENWEATHER_API_KEY, REQUEST_TIMEOUT_SECONDS

HEADERS = {"User-Agent": JARVIS_USER_AGENT}
API_KEY = OPENWEATHER_API_KEY
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{topic}"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

def search_web(query):
    try:
        # Wikipedia URL construction now quotes path segments instead of hand-concatenating strings.
        url = WIKIPEDIA_SUMMARY_URL.format(topic=quote(str(query).replace(" ", "_"), safe="_"))
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        if r.status_code == 200:
            data = r.json()
            if "extract" in data:
                sentences = data["extract"].split(". ")
                return ". ".join(sentences[:2]) + "."
        return "I could not find anything on that topic Sir."
    except Exception as e:
        return f"Search failed Sir: {str(e)}"

def get_weather(city="Hyderabad"):
    if not API_KEY:
        # Missing weather credentials are reported at call time instead of relying on committed keys.
        return "Weather API key is not configured. Set OPENWEATHER_API_KEY before using weather."

    try:
        # Weather requests reuse shared env config so credentials are not hardcoded.
        params = {"q": city, "appid": API_KEY, "units": "metric"}
        r = requests.get(f"{OPENWEATHER_URL}?{urlencode(params)}", headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        if r.status_code == 200:
            data = r.json()
            temp = data["main"]["temp"]
            feels = data["main"]["feels_like"]
            desc = data["weather"][0]["description"]
            hum = data["main"]["humidity"]
            name = data["name"]
            return f"{name}: {desc}, {temp} degrees celsius, feels like {feels}, humidity {hum} percent"
        return "Could not get weather Sir."
    except Exception as e:
        return f"Weather failed: {str(e)}"
