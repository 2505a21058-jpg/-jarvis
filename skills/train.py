import os
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

if not RAPIDAPI_KEY:
    raise ValueError("RAPIDAPI_KEY not found in .env file. Please add it to .env")

HEADERS = {
    "X-RapidAPI-Host": "indian-railway-pnr-status.p.rapidapi.com",
    "X-RapidAPI-Key": RAPIDAPI_KEY
}

def check_pnr(pnr_number):
    try:
        url = f"https://indian-railway-pnr-status.p.rapidapi.com/getPNRStatus/{pnr_number}/"
        response = requests.get(url, headers=HEADERS, timeout=10)
        
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
    try:
        url = f"https://indian-railway-pnr-status.p.rapidapi.com/getLiveTrainStatus/{train_number}/"
        response = requests.get(url, headers=HEADERS, timeout=10)
        
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