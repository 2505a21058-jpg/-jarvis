import requests

HEADERS = {"User-Agent": "JARVIS/1.0 (personal project)"}
API_KEY = "6838336d63ee9dd6a2e56f37a0870f81"

def search_web(query):
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_")
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "extract" in data:
                sentences = data["extract"].split(". ")
                return ". ".join(sentences[:2]) + "."
        return "I could not find anything on that topic Sir."
    except Exception as e:
        return f"Search failed Sir: {str(e)}"

def get_weather(city="Hyderabad"):
    try:
        url = "https://api.openweathermap.org/data/2.5/weather?q=" + city + "&appid=" + API_KEY + "&units=metric"
        r = requests.get(url, headers=HEADERS, timeout=10)
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
