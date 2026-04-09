from execution_engine import command_exists, launch_system_command
from memory.context import SESSION_CONTEXT

CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
CHROME_PROFILE = "C:\\Users\\shiva\\AppData\\Local\\Google\\Chrome\\User Data"
PROFILE_DIR = "Profile 3"


def _launch_app(command, success_message: str, fallback_command=None, context_name: str = ""):
    result = launch_system_command(command)
    if result.ok:
        if context_name:
            SESSION_CONTEXT.set_app(context_name)
        return success_message

    if fallback_command is not None:
        fallback_result = launch_system_command(fallback_command)
        if fallback_result.ok:
            if context_name:
                SESSION_CONTEXT.set_app(context_name)
            return success_message
        error = fallback_result.error or result.error
        return f"Failed to open app: {error}"

    return f"Failed to open app: {result.error or 'unknown error'}"


def open_chrome(url=None):
    cmd = [CHROME, "--new-window", "--user-data-dir=" + CHROME_PROFILE, "--profile-directory=" + PROFILE_DIR]
    if url:
        cmd.append(url)

    if command_exists(CHROME):
        return _launch_app(cmd, "Chrome is open Sir.", context_name="chrome")

    fallback = ["cmd", "/c", "start", "", "chrome"]
    if url:
        fallback.append(url)
    return _launch_app(fallback, "Chrome is open Sir.", context_name="chrome")

def open_app(app_name, url=None):
    app_name = app_name.lower().strip()
    if any(w in app_name for w in ["chrome", "browser", "google"]):
        return open_chrome(url)
    elif any(w in app_name for w in ["notepad", "note"]):
        return _launch_app(["notepad.exe"], "Notepad is open Sir.", context_name="notepad")
    elif any(w in app_name for w in ["calculator", "calc"]):
        return _launch_app(["calc.exe"], "Calculator is open Sir.", context_name="calculator")
    elif any(w in app_name for w in ["files", "explorer", "folder"]):
        return _launch_app(["explorer.exe"], "File Explorer is open Sir.", context_name="explorer")
    return f"I dont know how to open {app_name} Sir."
