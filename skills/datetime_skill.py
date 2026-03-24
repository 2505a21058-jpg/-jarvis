from datetime import datetime

def get_time():
    now = datetime.now()
    return f"The time is {now.strftime('%I:%M %p')} Sir."

def get_date():
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d %Y')} Sir."

def get_datetime():
    return get_time() + " " + get_date()
