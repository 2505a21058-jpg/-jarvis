import subprocess

CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
CHROME_PROFILE = "C:\\Users\\shiva\\AppData\\Local\\Google\\Chrome\\User Data"
PROFILE_DIR = "Profile 3"

def open_chrome(url=None):
    cmd = [CHROME, "--new-window", "--user-data-dir=" + CHROME_PROFILE, "--profile-directory=" + PROFILE_DIR]
    if url:
        cmd.append(url)
    subprocess.Popen(cmd)
    return "Chrome is open Sir."

def open_app(app_name, url=None):
    app_name = app_name.lower().strip()
    if any(w in app_name for w in ["chrome", "browser", "google"]):
        return open_chrome(url)
    elif any(w in app_name for w in ["notepad", "note"]):
        subprocess.Popen("notepad.exe")
        return "Notepad is open Sir."
    elif any(w in app_name for w in ["calculator", "calc"]):
        subprocess.Popen("calc.exe")
        return "Calculator is open Sir."
    elif any(w in app_name for w in ["files", "explorer", "folder"]):
        subprocess.Popen("explorer.exe")
        return "File Explorer is open Sir."
    return f"I dont know how to open {app_name} Sir."
