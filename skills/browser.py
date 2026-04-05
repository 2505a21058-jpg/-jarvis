from playwright.sync_api import sync_playwright
import time
import re
from urllib.parse import quote_plus

_playwright = None
_browser = None
_page = None
_browser_context = None
_pages = []
NAVIGATION_WAIT_UNTIL = "domcontentloaded"
NAVIGATION_TIMEOUT_MS = 10000

BANGS = {
    "youtube": "!yt",
    "amazon": "!amz",
    "github": "!gh",
    "maps": "!maps",
    "google maps": "!maps",
    "reddit": "!reddit",
    "wikipedia": "!w",
    "wiki": "!w",
    "stackoverflow": "!so",
    "stack overflow": "!so",
    "twitter": "!twitter",
    "instagram": "!instagram",
    "flipkart": "!flipkart",
    "netflix": "!netflix",
    "spotify": "!spotify",
    "translate": "!translate",
    "news": "!gnews",
    "images": "!gi",
    "google": "!g",
}

SITE_HINTS = {
    "youtube", "github", "amazon", "reddit", "wikipedia", "stackoverflow",
    "twitter", "instagram", "flipkart", "netflix", "spotify", "google", "irctc"
}

KNOWN_SERVICE_URLS = {
    "google maps": "https://www.google.com/maps",
    "maps": "https://www.google.com/maps",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
}

BROWSE_PREFIXES = ("open ", "search for ", "search ", "find ", "look up ", "show me ")

def get_bang(task):
    task_lower = task.lower()
    for key, bang in BANGS.items():
        if key in task_lower:
            query = task_lower.replace(key, "").replace("search", "").replace(" for ", " ").replace(" on ", " ").strip()
            return bang, query
    query = task_lower.replace("search", "").replace(" for ", " ").replace(" on ", " ").strip()
    return None, query

def build_duckduckgo_url(query):
    return f"https://duckduckgo.com/?q={quote_plus(query)}"


def strip_browse_prefix(task):
    text = task.strip()
    lowered = text.lower()
    for prefix in BROWSE_PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def resolve_browse_target(task):
    text = strip_browse_prefix(task)
    lowered = text.lower().strip(" .?!")

    if not lowered:
        return "https://duckduckgo.com", "Opened browser Sir.", ""

    if text.startswith(("http://", "https://")):
        return text, f"Opened {text} Sir.", lowered

    if re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", lowered):
        url = f"https://{lowered}"
        return url, f"Opened {url} Sir.", lowered

    if lowered in KNOWN_SERVICE_URLS:
        url = KNOWN_SERVICE_URLS[lowered]
        return url, f"Opened {url} Sir.", lowered

    if re.fullmatch(r"[a-z0-9-]+", lowered):
        url = f"https://{lowered}.com"
        return url, f"Opened {url} Sir.", lowered

    url = build_duckduckgo_url(text)
    return url, f"Searched for {text} Sir.", text

def solve_captcha(page):
    try:
        captcha_text = page.inner_text("label[for=inputCaptcha]")
        numbers = re.findall(r"\d+", captcha_text)
        if len(numbers) >= 2:
            if "+" in captcha_text:
                answer = int(numbers[0]) + int(numbers[1])
            elif "-" in captcha_text:
                answer = int(numbers[0]) - int(numbers[1])
            elif "*" in captcha_text:
                answer = int(numbers[0]) * int(numbers[1])
            else:
                answer = int(numbers[0]) + int(numbers[1])
            page.fill("input#inputCaptcha", str(answer))
            time.sleep(0.5)
            return True
    except:
        pass
    return False


def open_in_tab(page, url):
    page.goto(url, wait_until=NAVIGATION_WAIT_UNTIL, timeout=NAVIGATION_TIMEOUT_MS)
    page.bring_to_front()

def get_page():
    global _playwright, _browser, _page, _browser_context, _pages
    if _playwright is None:
        _playwright = sync_playwright().start()
    if _browser is None:
        _browser = _playwright.firefox.launch(headless=False)
    if _browser_context is None:
        _browser_context = _browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        )
    _page = _browser_context.new_page()
    _pages.append(_page)
    return _page

def browse(task):
    page = get_page()

    try:
        if any(w in task.lower() for w in ["pnr", "train status"]):
            pnr = re.search(r"\d{10}", task)
            if pnr:
                pnr_number = pnr.group()
                open_in_tab(page, "https://www.indianrail.gov.in/enquiry/PNR/PnrEnquiry.html?locale=en")
                time.sleep(1)
                try:
                    page.fill("input#inputPnrNo", pnr_number)
                    time.sleep(0.5)
                    solved = solve_captcha(page)
                    if solved:
                        page.click("button#modal1")
                        time.sleep(1)
                        return f"PNR {pnr_number} status is being fetched Sir."
                    else:
                        return f"PNR entered Sir. Please solve the captcha manually."
                except Exception as e:
                    return f"PNR page opened Sir. Please enter {pnr_number} manually."
            else:
                return "Please provide a 10 digit PNR number Sir."

        elif any(w in task.lower() for w in ["train", "irctc"]):
            open_in_tab(page, "https://www.irctc.co.in")
            return "Opened IRCTC Sir. Tell me source, destination and date to proceed."

        else:
            target_url, message, fallback_query = resolve_browse_target(task)
            try:
                open_in_tab(page, target_url)
                return message
            except Exception:
                fallback_url = build_duckduckgo_url(fallback_query or strip_browse_prefix(task) or task)
                open_in_tab(page, fallback_url)
                return f"Searched for {fallback_query or strip_browse_prefix(task) or task} Sir."

    except Exception as e:
        return f"Browser error Sir: {str(e)}"

def close_browser():
    global _playwright, _browser, _page, _browser_context, _pages
    errors = []

    pages = list(_pages)
    context = _browser_context
    browser = _browser
    playwright = _playwright

    _page = None
    _browser_context = None
    _browser = None
    _playwright = None
    _pages = []

    for page in pages:
        try:
            if not page.is_closed():
                page.close()
        except Exception as e:
            errors.append(f"page close failed: {e}")

    if context is not None:
        try:
            context.close()
        except Exception as e:
            errors.append(f"context close failed: {e}")

    if browser is not None:
        try:
            browser.close()
        except Exception as e:
            errors.append(f"browser close failed: {e}")

    if playwright is not None:
        try:
            playwright.stop()
        except Exception as e:
            errors.append(f"playwright stop failed: {e}")

    return errors

if __name__ == "__main__":
    print(browse("check pnr 1234567890"))
    input("Press enter to close...")
    close_browser()
