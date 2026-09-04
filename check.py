import json
import os
import smtplib
from email.message import EmailMessage

from playwright.sync_api import sync_playwright


PRODUCT_URL = os.environ.get(
    "PRODUCT_URL",
    "https://samuraistore.site/rental-games"
)

GAME_TITLE = "007 First Light"
STATE_FILE = "state.json"

GMAIL_USERNAME = os.environ["GMAIL_USERNAME"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ALERT_TO = os.environ["ALERT_TO"]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_status": "unknown"}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {"last_status": "unknown"}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)


def send_email(subject, message_text):
    message = EmailMessage()
    message["From"] = GMAIL_USERNAME
    message["To"] = ALERT_TO
    message["Subject"] = subject
    message.set_content(message_text)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USERNAME, GMAIL_APP_PASSWORD)
        smtp.send_message(message)


def get_status():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(
                PRODUCT_URL,
                wait_until="networkidle",
                timeout=60_000
            )

            page.wait_for_timeout(3_000)

            game = page.get_by_text(GAME_TITLE, exact=False).first

            if game.count() == 0:
                print(f"Could not find '{GAME_TITLE}'.")
                return "not_found"

            # Get surrounding text from the game's listing/card.
            listing = game.locator(
                "xpath=ancestor::*[self::article or "
                "self::li or contains(@class, 'card') or "
                "contains(@class, 'product') or "
                "contains(@class, 'game')][1]"
            )

            if listing.count() == 0:
                listing = game.locator("xpath=..")

            text = listing.inner_text().lower()

            print("Game listing text:")
            print(text)

            # Check unavailable words first.
            if any(word in text for word in [
                "rented",
                "unavailable",
                "not available",
                "out of stock"
            ]):
                return "rented"

            if any(word in text for word in [
                "available",
                "in stock",
                "rent now"
            ]):
                return "available"

            return "unknown"

        finally:
            browser.close()


def run_check():
    state = load_state()
    previous_status = state.get("last_status", "unknown")
    current_status = get_status()

    print(f"Previous status: {previous_status}")
    print(f"Current status: {current_status}")

    if current_status == "not_found":
        print("The game was not found. State was not changed.")
        return

    # Alert only when the game changes into available status.
    if (
        current_status == "available"
        and previous_status != "available"
    ):
        send_email(
            subject=f"{GAME_TITLE} is available",
            message_text=(
                f"{GAME_TITLE} is now available to rent.\n\n"
                f"Check it here:\n{PRODUCT_URL}"
            )
        )
        print("Availability email sent.")

    elif current_status == "available":
        print("The game is still available. No new email sent.")

    elif current_status == "rented":
        print("The game is rented. No email sent.")

    else:
        print("Availability could not be determined. No email sent.")

    state["last_status"] = current_status
    save_state(state)


def run_daily():
    status = get_status()

    if status == "not_found":
        status_message = (
            f"Could not find '{GAME_TITLE}' on the page."
        )
    else:
        status_message = (
            f"Current status of {GAME_TITLE}: {status}"
        )

    send_email(
        subject=f"Daily rental update: {GAME_TITLE}",
        message_text=(
            f"{status_message}\n\n"
            f"Check the page here:\n{PRODUCT_URL}"
        )
    )

    print("Daily status email sent.")


if __name__ == "__main__":
    mode = os.environ.get("CHECK_MODE", "check")

    if mode == "daily":
        run_daily()
    else:
        run_check()
