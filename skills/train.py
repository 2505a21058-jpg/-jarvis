import requests

from config import RAPIDAPI_KEY, REQUEST_TIMEOUT_SECONDS

RAILWAY_API_HOST = "indian-railway-pnr-status.p.rapidapi.com"
RAILWAY_API_BASE_URL = f"https://{RAILWAY_API_HOST}"

HEADERS = {
    "X-RapidAPI-Host": RAILWAY_API_HOST,
    "X-RapidAPI-Key": RAPIDAPI_KEY
}

def _headers_or_error():
    # RapidAPI credentials are checked at call time so importing optional skills never crashes startup.
    if not RAPIDAPI_KEY:
        return None, "RAPIDAPI_KEY is not configured. Add it before using train lookups."
    return HEADERS, ""

def check_pnr(pnr_number):
    headers, error = _headers_or_error()
    if error:
        return error

    try:
        url = f"{RAILWAY_API_BASE_URL}/getPNRStatus/{pnr_number}/"
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("PnrNumber"):
                pnr = data["PnrNumber"]
                train = data.get("TrainName", "Unknown")
                train_no = data.get("TrainNumber", "")
                date = data.get("DateOfJourney", "")
                from_station = data.get("From", "")
                to_station = data.get("To", "")
                status = data.get("PassengerList", [{}])[0].get("CurrentStatus", "Unknown")
                coach = data.get("PassengerList", [{}])[0].get("Coach", "")
                berth = data.get("PassengerList", [{}])[0].get("BerthNo", "")
                
                result = f"PNR {pnr}. Train {train} number {train_no}. Date {date}. From {from_station} to {to_station}. Status {status}."
                if coach:
                    result += f" Coach {coach}, Berth {berth}."
                return result
            else:
                return "Could not fetch PNR status. Please check the PNR number."
        else:
            return f"PNR check failed. Status code {response.status_code}."
            
    except Exception as e:
        return f"PNR check error: {str(e)}"

def get_live_train(train_number):
    headers, error = _headers_or_error()
    if error:
        return error

    try:
        url = f"{RAILWAY_API_BASE_URL}/getLiveTrainStatus/{train_number}/"
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            train_name = data.get("TrainName", "Unknown")
            current_station = data.get("CurrentStation", "Unknown")
            delay = data.get("DelayInfo", "No delay info")
            return f"Train {train_name}. Currently at {current_station}. Delay info: {delay}."
        else:
            return "Could not fetch live train status."
            
    except Exception as e:
        return f"Live train error: {str(e)}"

if __name__ == "__main__":
    pnr = input("Enter PNR number: ")
    print(check_pnr(pnr))
