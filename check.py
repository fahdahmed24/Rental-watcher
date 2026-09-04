import os
import json
import argparse
from playwright.sync_api import sync_playwright
import smtplib
from email.mime.text import MIMEText

PRODUCT_URL = os.environ["https://samuraistore.site/rental-games"]
GAME_TITLE = "007 First Light"
GMAIL_ADDRESS = "faybs646@gmail.com"
GMAIL_APP_PASSWORD = os.environ["ssdeitdvbsmwaxzu"]
TO_EMAIL = "faybs646@gmail.com"
STATE_FILE = "state.json"
MAX_NOTIFICATIONS = 6  # 6 x 5 min = 30 min of alerts

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_status": "unknown", "notify_count": 0}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def get_status():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(PRODUCT_URL, wait_until="networkidle", timeout=30000)

        cards = page.locator("article.rental-game-card")
        status = "not_found"

        for i in range(cards.count()):
            card = cards.nth(i)
            alt = card.locator("img").get_attribute("alt") or ""
            if GAME_TITLE.lower() in alt.lower():
                badge_class = card.locator(".rental-stock-badge").get_attribute("class") or ""
                status = "rented" if "rental-stock-rented" in badge_class else "available"
                break

        browser.close()
        return status

def run_check():
    state = load_state()
    status = get_status()

    if status == "not_found":
        print(f"Could not find '{GAME_TITLE}'.")
        return

    if status == "available":
        if state["last_status"] != "available":
            state["notify_count"] = 0  # just became available — start a fresh burst
        if state["notify_count"] < MAX_NOTIFICATIONS:
            send_email(f"🎮 {GAME_TITLE} is available now!", f"Go grab it: {PRODUCT_URL}")
            state["notify_count"] += 1
            print(f"Email sent ({state['notify_count']}/{MAX_NOTIFICATIONS}).")
        else:
            print("Still available, but already sent 6 alerts.")
    else:
        state["notify_count"] = 0
        print("Still rented — no email.")

    state["last_status"] = status
    save_state(state)

def run_daily():
    status = get_status()
    body = {
        "available": f"Still available right now: {PRODUCT_URL}",
        "rented": f"Still rented, not available yet: {PRODUCT_URL}",
        "not_found": f"Couldn't find '{GAME_TITLE}' — check the site.",
    }[status]
    send_email(f"📋 Daily update: {GAME_TITLE}", body)
    print("Daily update sent.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "daily"], default="check")
    args = parser.parse_args()
    run_check() if args.mode == "check" else run_daily()
