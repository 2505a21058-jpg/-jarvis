import requests
from rich.console import Console

console = Console()

API_KEY = "6838336d63ee9dd6a2e56f37a0870f81"
HEADERS = {"User-Agent": "JARVIS/1.0 (personal project)"}

def get_weather(city="Hyderabad"):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
        response = requests.get(url, headers=HEADERS, timeout=10)
        
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
    print(get_weather("Hyderabad"))mkdir jarvis