from playwright.sync_api import sync_playwright
import time
import re

_playwright = None
_browser = None
_page = None

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

def get_bang(task):
    task_lower = task.lower()
    for key, bang in BANGS.items():
        if key in task_lower:
            query = task_lower.replace(key, "").replace("search", "").replace(" for ", " ").replace(" on ", " ").strip()
            return bang, query
    query = task_lower.replace("search", "").replace(" for ", " ").replace(" on ", " ").strip()
    return None, query

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

def get_page():
    global _playwright, _browser, _page
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.firefox.launch(headless=False)
        context = _browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        )
        _page = context.new_page()
    return _page

def browse(task):
    page = get_page()

    try:
        if any(w in task.lower() for w in ["pnr", "train status"]):
            pnr = re.search(r"\d{10}", task)
            if pnr:
                pnr_number = pnr.group()
                page.goto("https://www.indianrail.gov.in/enquiry/PNR/PnrEnquiry.html?locale=en")
                time.sleep(3)
                try:
                    page.fill("input#inputPnrNo", pnr_number)
                    time.sleep(1)
                    solved = solve_captcha(page)
                    if solved:
                        page.click("button#modal1")
                        time.sleep(3)
                        return f"PNR {pnr_number} status is being fetched Sir."
                    else:
                        return f"PNR entered Sir. Please solve the captcha manually."
                except Exception as e:
                    return f"PNR page opened Sir. Please enter {pnr_number} manually."
            else:
                return "Please provide a 10 digit PNR number Sir."

        elif any(w in task.lower() for w in ["search", "find", "look up", "show me"]):
            bang, query = get_bang(task)
            if bang:
                search_query = f"{bang} {query}"
            else:
                search_query = query
            page.goto(f"https://duckduckgo.com/?q={search_query.replace(' ', '+')}")
            time.sleep(3)
            return f"Searched for {query} Sir."

        elif any(w in task.lower() for w in ["train", "irctc"]):
            page.goto("https://www.irctc.co.in")
            time.sleep(3)
            return "Opened IRCTC Sir. Tell me source, destination and date to proceed."

        elif "open" in task.lower():
            bang, _ = get_bang(task)
            site = task.lower().replace("open", "").strip()
            if bang:
                page.goto(f"https://duckduckgo.com/?q={bang}")
                time.sleep(3)
                return f"Opened {site.strip()} Sir."
            if "." not in site:
                site = site + ".com"
            if not site.startswith("http"):
                site = "https://" + site
            page.goto(site)
            time.sleep(2)
            return f"Opened {site} Sir."

        else:
            page.goto("https://duckduckgo.com")
            return "Opened browser Sir."

    except Exception as e:
        return f"Browser error Sir: {str(e)}"

def close_browser():
    global _playwright, _browser, _page
    if _browser:
        _browser.close()
        _playwright.stop()
        _browser = None
        _page = None

if __name__ == "__main__":
    print(browse("check pnr 1234567890"))
    input("Press enter to close...")
    close_browser()
