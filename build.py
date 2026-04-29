"""
LEGACY HAZARD - DO NOT RUN IN PRODUCTION.
This file can overwrite runtime modules.
"""
import sys

if "--force" not in sys.argv:
    print("ERROR: build.py is a legacy hazard. Pass --force to run intentionally.")
    sys.exit(1)

content = '''from skills.web_search import search_web, get_weather
from skills.open_app import open_app
from skills.datetime_skill import get_time, get_date, get_datetime
from skills.browser import browse
from skills.train import check_pnr, get_live_train
import re

def handle_skill(user_input):
    text = user_input.lower().strip()

    if any(w in text for w in ["time", "date", "day", "today"]):
        if "time" in text:
            return get_time()
        return get_date()

    if any(w in text for w in ["weather", "temperature", "forecast"]):
        city = "Hyderabad"
        words = text.split()
        for i, w in enumerate(words):
            if w == "in" and i + 1 < len(words):
                city = words[i + 1]
        return get_weather(city)

    if any(w in text for w in ["pnr", "check pnr", "pnr status"]):
        pnr = re.search(r"\\d{10}", text)
        if pnr:
            return check_pnr(pnr.group())
        return "Please provide a 10 digit PNR number Sir."

    if any(w in text for w in ["live train", "train location", "where is train"]):
        train = re.search(r"\\d{4,5}", text)
        if train:
            return get_live_train(train.group())
        return "Please provide a train number Sir."

    if any(w in text for w in ["open", "launch", "start"]):
        if any(w in text for w in ["chrome", "browser"]):
            return open_app("chrome")
        elif any(w in text for w in ["notepad", "note"]):
            return open_app("notepad")
        elif any(w in text for w in ["calculator", "calc"]):
            return open_app("calculator")
        elif any(w in text for w in ["files", "explorer"]):
            return open_app("explorer")
        elif any(w in text for w in ["youtube", "spotify", "netflix", "reddit", "amazon", "irctc"]):
            return browse(f"open {text}")

    if any(w in text for w in ["search", "find", "look up", "show me"]):
        return browse(text)

    if any(w in text for w in ["train", "irctc", "book ticket"]):
        return browse(text)

    if any(w in text for w in ["who is", "what is", "tell me about"]):
        query = text
        for p in ["who is", "what is", "tell me about"]:
            query = query.replace(p, "").strip()
        return search_web(query)

    return None
'''

with open("skills/router.py", "w") as f:
    f.write(content)
print("router.py updated!")
