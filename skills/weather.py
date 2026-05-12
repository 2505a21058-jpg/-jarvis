from urllib.parse import urlencode

import requests
from rich.console import Console

from config import JARVIS_USER_AGENT, OPENWEATHER_API_KEY, REQUEST_TIMEOUT_SECONDS

console = Console()

API_KEY = OPENWEATHER_API_KEY
HEADERS = {"User-Agent": JARVIS_USER_AGENT}
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

def get_weather(city="Hyderabad"):
    if not API_KEY:
        # Missing weather credentials are reported at call time instead of relying on committed keys.
        return "Weather API key is not configured. Set OPENWEATHER_API_KEY before using weather."

    try:
        # Weather requests now build params explicitly so credentials stay in env config.
        params = {"q": city, "appid": API_KEY, "units": "metric"}
        response = requests.get(f"{OPENWEATHER_URL}?{urlencode(params)}", headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            description = data['weather'][0]['description']
            humidity = data['main']['humidity']
            city_name = data['name']
            
            return f"{city_name}: {description}, {temp}°C, feels like {feels_like}°C, humidity {humidity}%"
        
        elif response.status_code == 401:
            return "Weather API key is invalid Sir."
        elif response.status_code == 404:
            return f"City {city} not found Sir."
        else:
            return "Couldn't get weather Sir."
            
    except Exception as e:
        return f"Weather fetch failed: {str(e)}"

if __name__ == "__main__":
    print(get_weather("Hyderabad"))
