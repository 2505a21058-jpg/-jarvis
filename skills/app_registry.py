from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus


@dataclass
class AppCapability:
    """Capabilities and identifiers for a single app."""
    name: str
    display_name: str = ""
    category: str = ""
    search_url: Optional[str] = None
    supports_search: bool = False
    supports_play: bool = False
    web_url: Optional[str] = None
    executables: list[str] = field(default_factory=list)
    mac_apps: list[str] = field(default_factory=list)
    linux_apps: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


class AppRegistry:
    """Single source of truth for all app capabilities."""

    def __init__(self):
        self._apps: dict[str, AppCapability] = {}
        self._aliases: dict[str, str] = {}

    def register(self, cap: AppCapability) -> None:
        key = cap.name.lower()
        self._apps[key] = cap
        for alias in cap.aliases:
            self._aliases[alias.lower()] = key

    def get(self, name: str) -> Optional[AppCapability]:
        key = name.lower().strip()
        if key in self._apps:
            return self._apps[key]
        if key in self._aliases:
            resolved = self._aliases[key]
            return self._apps.get(resolved)
        return None

    def resolve(self, name: str) -> str:
        key = name.lower().strip()
        if key in self._apps:
            return self._apps[key].name
        if key in self._aliases:
            resolved = self._aliases[key]
            return self._apps[resolved].name if resolved in self._apps else name
        return name

    def is_browser(self, name: str) -> bool:
        cap = self.get(name)
        return cap is not None and cap.category == "browser"

    def supports_search(self, name: str) -> bool:
        cap = self.get(name)
        return cap is not None and cap.supports_search

    def supports_play(self, name: str) -> bool:
        cap = self.get(name)
        return cap is not None and cap.supports_play

    def search_url_for(self, name: str, query: str) -> Optional[str]:
        cap = self.get(name)
        if cap and cap.search_url:
            return cap.search_url.replace("{query}", quote_plus(query))
        return None

    def searchable_apps(self) -> list[str]:
        return [cap.name for cap in self._apps.values() if cap.supports_search]

    def playable_apps(self) -> list[str]:
        return [cap.name for cap in self._apps.values() if cap.supports_play]

    def browsers(self) -> list[str]:
        return [cap.name for cap in self._apps.values() if cap.category == "browser"]

    def web_services(self) -> list[str]:
        return [cap.name for cap in self._apps.values() if cap.web_url is not None]

    def all_apps(self) -> dict[str, AppCapability]:
        return dict(self._apps)

    def all_names(self) -> list[str]:
        return list(self._apps.keys())

    def _register_defaults(self):
        """Register every known app consolidated from open_app.py, open_and_search.py, open_search_and_play.py."""

        # ── Browsers ──────────────────────────────────────────────
        self.register(AppCapability(
            name="chrome", display_name="Google Chrome",
            category="browser",
            executables=["chrome.exe"],
            mac_apps=["Google Chrome"],
            linux_apps=["google-chrome", "chromium-browser"],
            aliases=["google chrome", "chromium", "google-chrome"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
            web_url="https://www.google.com",
        ))
        self.register(AppCapability(
            name="firefox", display_name="Mozilla Firefox",
            category="browser",
            executables=["firefox.exe"],
            mac_apps=["Firefox"],
            linux_apps=["firefox"],
            aliases=["mozilla firefox", "ff"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
            web_url="https://www.mozilla.org/firefox",
        ))
        self.register(AppCapability(
            name="msedge", display_name="Microsoft Edge",
            category="browser",
            executables=["msedge.exe"],
            mac_apps=["Microsoft Edge"],
            linux_apps=["microsoft-edge"],
            aliases=["edge", "microsoft edge"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
        ))
        self.register(AppCapability(
            name="brave", display_name="Brave",
            category="browser",
            executables=["brave.exe"],
            mac_apps=["Brave Browser"],
            linux_apps=["brave-browser"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
        ))
        self.register(AppCapability(
            name="opera", display_name="Opera",
            category="browser",
            executables=["opera.exe"],
            mac_apps=["Opera"],
            linux_apps=["opera"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
        ))
        self.register(AppCapability(
            name="vivaldi", display_name="Vivaldi",
            category="browser",
            executables=["vivaldi.exe"],
            mac_apps=["Vivaldi"],
            linux_apps=["vivaldi"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
        ))
        self.register(AppCapability(
            name="safari", display_name="Safari",
            category="browser",
            executables=[],
            mac_apps=["Safari"],
            linux_apps=[],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
        ))
        # Generic catch-all for "browser" alias
        self.register(AppCapability(
            name="browser", display_name="Default Browser",
            category="browser",
            aliases=["web browser", "internet browser"],
            supports_search=True,
            search_url="https://www.google.com/search?q={query}",
        ))

        # ── Search engines ────────────────────────────────────────
        self.register(AppCapability(
            name="google", display_name="Google",
            category="web_service",
            web_url="https://www.google.com",
            search_url="https://www.google.com/search?q={query}",
            supports_search=True,
            aliases=["google search"],
        ))
        self.register(AppCapability(
            name="bing", display_name="Bing",
            category="web_service",
            web_url="https://www.bing.com",
            search_url="https://www.bing.com/search?q={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="duckduckgo", display_name="DuckDuckGo",
            category="web_service",
            web_url="https://duckduckgo.com",
            search_url="https://duckduckgo.com/?q={query}",
            supports_search=True,
            aliases=["ddg"],
        ))
        self.register(AppCapability(
            name="yahoo", display_name="Yahoo!",
            category="web_service",
            web_url="https://www.yahoo.com",
            search_url="https://search.yahoo.com/search?p={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="yandex", display_name="Yandex",
            category="web_service",
            web_url="https://yandex.com",
            search_url="https://yandex.com/search/?text={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="baidu", display_name="Baidu",
            category="web_service",
            web_url="https://www.baidu.com",
            search_url="https://www.baidu.com/s?wd={query}",
            supports_search=True,
        ))

        # ── Media / Video / Music ─────────────────────────────────
        self.register(AppCapability(
            name="youtube", display_name="YouTube",
            category="media",
            web_url="https://www.youtube.com",
            search_url="https://www.youtube.com/results?search_query={query}",
            supports_search=True,
            supports_play=True,
            aliases=["yt", "youtube music"],
        ))
        self.register(AppCapability(
            name="spotify", display_name="Spotify",
            category="media",
            web_url="https://open.spotify.com",
            search_url="https://open.spotify.com/search/{query}",
            supports_search=True,
            supports_play=True,
            executables=["Spotify.exe"],
            mac_apps=["Spotify"],
        ))
        self.register(AppCapability(
            name="soundcloud", display_name="SoundCloud",
            category="media",
            web_url="https://soundcloud.com",
            search_url="https://soundcloud.com/search?q={query}",
            supports_search=True,
            supports_play=True,
        ))
        self.register(AppCapability(
            name="netflix", display_name="Netflix",
            category="media",
            web_url="https://www.netflix.com",
        ))
        self.register(AppCapability(
            name="youtube music", display_name="YouTube Music",
            category="media",
            web_url="https://music.youtube.com",
            search_url="https://music.youtube.com/search?q={query}",
            supports_search=True,
            supports_play=True,
            aliases=["yt music"],
        ))

        # ── Social / Communication ────────────────────────────────
        self.register(AppCapability(
            name="twitter", display_name="Twitter / X",
            category="social",
            web_url="https://twitter.com",
            search_url="https://twitter.com/search?q={query}",
            supports_search=True,
            aliases=["x"],
        ))
        self.register(AppCapability(
            name="reddit", display_name="Reddit",
            category="social",
            web_url="https://www.reddit.com",
            search_url="https://www.reddit.com/search/?q={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="instagram", display_name="Instagram",
            category="social",
            web_url="https://www.instagram.com",
            search_url="https://www.instagram.com/explore/search/keyword/?q={query}",
            supports_search=True,
            aliases=["ig"],
        ))
        self.register(AppCapability(
            name="facebook", display_name="Facebook",
            category="social",
            web_url="https://www.facebook.com",
            search_url="https://www.facebook.com/search/top?q={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="linkedin", display_name="LinkedIn",
            category="social",
            web_url="https://www.linkedin.com",
            search_url="https://www.linkedin.com/search/results/all/?keywords={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="pinterest", display_name="Pinterest",
            category="social",
            web_url="https://www.pinterest.com",
            search_url="https://www.pinterest.com/search/pins/?q={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="tiktok", display_name="TikTok",
            category="social",
            web_url="https://www.tiktok.com",
        ))
        self.register(AppCapability(
            name="whatsapp", display_name="WhatsApp",
            category="communication",
            web_url="https://web.whatsapp.com",
        ))
        self.register(AppCapability(
            name="telegram", display_name="Telegram",
            category="communication",
            web_url="https://web.telegram.org",
            executables=["Telegram.exe"],
        ))
        self.register(AppCapability(
            name="discord", display_name="Discord",
            category="communication",
            web_url="https://discord.com/app",
            executables=["Discord.exe"],
        ))
        self.register(AppCapability(
            name="slack", display_name="Slack",
            category="communication",
            web_url="https://slack.com",
            executables=["slack.exe"],
        ))
        self.register(AppCapability(
            name="zoom", display_name="Zoom",
            category="communication",
            web_url="https://zoom.us",
            executables=["Zoom.exe"],
            mac_apps=["zoom.us"],
        ))
        self.register(AppCapability(
            name="outlook", display_name="Microsoft Outlook",
            category="communication",
            web_url="https://outlook.live.com",
            executables=["OUTLOOK.EXE"],
            mac_apps=["Microsoft Outlook"],
        ))

        # ── Productivity / Office ─────────────────────────────────
        self.register(AppCapability(
            name="gmail", display_name="Gmail",
            category="productivity",
            web_url="https://mail.google.com",
            aliases=["google mail", "mail"],
        ))
        self.register(AppCapability(
            name="google drive", display_name="Google Drive",
            category="productivity",
            web_url="https://drive.google.com",
            aliases=["drive", "gdrive"],
        ))
        self.register(AppCapability(
            name="google docs", display_name="Google Docs",
            category="productivity",
            web_url="https://docs.google.com",
            aliases=["docs", "gdocs"],
        ))
        self.register(AppCapability(
            name="google sheets", display_name="Google Sheets",
            category="productivity",
            web_url="https://sheets.google.com",
            aliases=["sheets", "gsheets"],
        ))
        self.register(AppCapability(
            name="google meet", display_name="Google Meet",
            category="productivity",
            web_url="https://meet.google.com",
            aliases=["meet", "gmeet"],
        ))
        self.register(AppCapability(
            name="google maps", display_name="Google Maps",
            category="productivity",
            web_url="https://maps.google.com",
            search_url="https://www.google.com/maps/search/{query}",
            supports_search=True,
            aliases=["maps"],
        ))
        self.register(AppCapability(
            name="notion", display_name="Notion",
            category="productivity",
            web_url="https://www.notion.so",
        ))
        self.register(AppCapability(
            name="trello", display_name="Trello",
            category="productivity",
            web_url="https://trello.com",
        ))
        self.register(AppCapability(
            name="medium", display_name="Medium",
            category="productivity",
            web_url="https://medium.com",
        ))

        # ── Developer ─────────────────────────────────────────────
        self.register(AppCapability(
            name="github", display_name="GitHub",
            category="developer",
            web_url="https://github.com",
            search_url="https://github.com/search?q={query}",
            supports_search=True,
            aliases=["gh"],
        ))
        self.register(AppCapability(
            name="stackoverflow", display_name="Stack Overflow",
            category="developer",
            web_url="https://stackoverflow.com",
            search_url="https://stackoverflow.com/search?q={query}",
            supports_search=True,
            aliases=["stack overflow", "so"],
        ))
        self.register(AppCapability(
            name="vscode", display_name="Visual Studio Code",
            category="developer",
            executables=["Code.exe"],
            mac_apps=["Visual Studio Code"],
            linux_apps=["code"],
            aliases=["code", "visual studio code", "vs code"],
        ))
        self.register(AppCapability(
            name="cursor", display_name="Cursor",
            category="developer",
            executables=["cursor.exe"],
            mac_apps=["Cursor"],
            linux_apps=["cursor"],
        ))
        self.register(AppCapability(
            name="notepad++", display_name="Notepad++",
            category="developer",
            executables=["notepad++.exe"],
            aliases=["npp"],
        ))

        # ── Shopping ──────────────────────────────────────────────
        self.register(AppCapability(
            name="amazon", display_name="Amazon",
            category="shopping",
            web_url="https://www.amazon.com",
            search_url="https://www.amazon.com/s?k={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="flipkart", display_name="Flipkart",
            category="shopping",
            web_url="https://www.flipkart.com",
            search_url="https://www.flipkart.com/search?q={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="ebay", display_name="eBay",
            category="shopping",
            web_url="https://www.ebay.com",
            search_url="https://www.ebay.com/sch/i.html?_nkw={query}",
            supports_search=True,
        ))
        self.register(AppCapability(
            name="etsy", display_name="Etsy",
            category="shopping",
            web_url="https://www.etsy.com",
            search_url="https://www.etsy.com/search?q={query}",
            supports_search=True,
        ))

        # ── Reference / Info ──────────────────────────────────────
        self.register(AppCapability(
            name="wikipedia", display_name="Wikipedia",
            category="reference",
            web_url="https://www.wikipedia.org",
            search_url="https://en.wikipedia.org/w/index.php?search={query}",
            supports_search=True,
            aliases=["wiki"],
        ))
        self.register(AppCapability(
            name="imdb", display_name="IMDb",
            category="reference",
            web_url="https://www.imdb.com",
            search_url="https://www.imdb.com/find?q={query}",
            supports_search=True,
            aliases=["internet movie database"],
        ))
        self.register(AppCapability(
            name="flickr", display_name="Flickr",
            category="reference",
            web_url="https://www.flickr.com",
            search_url="https://www.flickr.com/search/?text={query}",
            supports_search=True,
        ))

        # ── Windows built-in apps ─────────────────────────────────
        self.register(AppCapability(
            name="notepad", display_name="Notepad",
            category="utility",
            executables=["notepad.exe"],
            aliases=["note"],
        ))
        self.register(AppCapability(
            name="terminal", display_name="Terminal",
            category="utility",
            executables=["WindowsTerminal.exe", "wt.exe"],
            mac_apps=["Terminal"],
            linux_apps=["gnome-terminal", "konsole", "xterm"],
            aliases=["console", "command prompt"],
        ))
        self.register(AppCapability(
            name="cmd", display_name="Command Prompt",
            category="utility",
            executables=["cmd.exe"],
            aliases=["command prompt", "dos"],
        ))
        self.register(AppCapability(
            name="powershell", display_name="PowerShell",
            category="utility",
            executables=["powershell.exe", "pwsh.exe"],
            aliases=["ps"],
        ))
        self.register(AppCapability(
            name="calculator", display_name="Calculator",
            category="utility",
            executables=["calc.exe"],
            mac_apps=["Calculator"],
        ))
        self.register(AppCapability(
            name="calendar", display_name="Calendar",
            category="utility",
            executables=["outlookcal.exe"],
        ))
        self.register(AppCapability(
            name="camera", display_name="Camera",
            category="utility",
            executables=["WindowsCamera.exe"],
        ))
        self.register(AppCapability(
            name="clock", display_name="Clock",
            category="utility",
            executables=["Alarms.exe"],
        ))
        self.register(AppCapability(
            name="file explorer", display_name="File Explorer",
            category="utility",
            executables=["explorer.exe"],
            aliases=["explorer", "file manager"],
        ))
        self.register(AppCapability(
            name="paint", display_name="Paint",
            category="utility",
            executables=["mspaint.exe"],
            aliases=["mspaint", "ms paint"],
        ))
        self.register(AppCapability(
            name="snipping tool", display_name="Snipping Tool",
            category="utility",
            executables=["SnippingTool.exe"],
            aliases=["snip", "screenshot tool"],
        ))
        self.register(AppCapability(
            name="settings", display_name="Settings",
            category="utility",
            executables=["SystemSettings.exe"],
            aliases=["system settings", "windows settings"],
        ))
        self.register(AppCapability(
            name="control panel", display_name="Control Panel",
            category="utility",
            executables=["control.exe"],
            aliases=["control"],
        ))
        self.register(AppCapability(
            name="task manager", display_name="Task Manager",
            category="utility",
            executables=["Taskmgr.exe"],
            aliases=["taskmgr"],
        ))
        self.register(AppCapability(
            name="word", display_name="Microsoft Word",
            category="productivity",
            executables=["WINWORD.EXE"],
            mac_apps=["Microsoft Word"],
        ))
        self.register(AppCapability(
            name="excel", display_name="Microsoft Excel",
            category="productivity",
            executables=["EXCEL.EXE"],
            mac_apps=["Microsoft Excel"],
        ))
        self.register(AppCapability(
            name="powerpoint", display_name="Microsoft PowerPoint",
            category="productivity",
            executables=["POWERPNT.EXE"],
            mac_apps=["Microsoft PowerPoint"],
        ))
        self.register(AppCapability(
            name="onenote", display_name="Microsoft OneNote",
            category="productivity",
            executables=["ONENOTE.EXE"],
            mac_apps=["Microsoft OneNote"],
        ))
        self.register(AppCapability(
            name="steam", display_name="Steam",
            category="utility",
            executables=["Steam.exe"],
        ))
        self.register(AppCapability(
            name="calculator", display_name="Calculator",
            category="utility",
            executables=["calc.exe"],
            mac_apps=["Calculator"],
        ))


_SINGLETON: Optional[AppRegistry] = None


def get_app_registry() -> AppRegistry:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = AppRegistry()
        _SINGLETON._register_defaults()
    return _SINGLETON
