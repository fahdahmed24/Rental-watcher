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

            # Check multiple parent elements because the game status
            # may be in a parent card or listing element.
            parents = [
                game.locator("xpath=.."),
                game.locator("xpath=../.."),
                game.locator("xpath=../../.."),
                game.locator("xpath=../../../.."),
                game.locator("xpath=../../../../.."),
            ]

            checked_text = set()

            for parent in parents:
                if parent.count() == 0:
                    continue

                try:
                    text = parent.inner_text().lower().strip()
                except Exception:
                    continue

                if not text or text in checked_text:
                    continue

                checked_text.add(text)

                print("Checking listing text:")
                print(text)

                # Check unavailable words first.
                if any(word in text for word in [
                    "rented",
                    "currently rented",
                    "unavailable",
                    "not available",
                    "out of stock"
                ]):
                    return "rented"

                # These normally indicate that the game can be rented.
                if any(word in text for word in [
                    "available",
                    "in stock",
                    "rent now",
                    "borrow",
                    "add to cart"
                ]):
                    return "available"

                # A button simply named "Rent" usually means available.
                words = text.replace("\n", " ").split()

                if "rent" in words:
                    return "available"

            # Final fallback: inspect text around the game title.
            page_text = page.locator("body").inner_text().lower()
            title_position = page_text.find(GAME_TITLE.lower())

            if title_position >= 0:
                nearby_text = page_text[
                    max(0, title_position - 300):
                    title_position + 700
                ]

                print("Nearby page text:")
                print(nearby_text)

                if any(word in nearby_text for word in [
                    "rented",
                    "currently rented",
                    "unavailable",
                    "not available",
                    "out of stock"
                ]):
                    return "rented"

                if any(word in nearby_text for word in [
                    "available",
                    "in stock",
                    "rent now",
                    "borrow",
                    "add to cart"
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
        print("Game was not found. State was not changed.")
        return

    if (
        current_status == "available"
        and previous_status != "available"
    ):
        send_email(
            subject=f"{GAME_TITLE} is available",
            message_text=(
                f"{GAME_TITLE} is now available to rent.\n\n"
                f"Open the rental page:\n{PRODUCT_URL}"
            )
        )
        print("Availability email sent.")

    elif current_status == "available":
        print("Game is still available. No new email sent.")

    elif current_status == "rented":
        print("Game is rented. No email sent.")

    else:
        print("Availability could not be determined.")

    state["last_status"] = current_status
    save_state(state)


def run_daily():
    status = get_status()

    send_email(
        subject=f"Daily rental update: {GAME_TITLE}",
        message_text=(
            f"Current status: {status}\n\n"
            f"Open the rental page:\n{PRODUCT_URL}"
        )
    )

    print("Daily email sent.")


if __name__ == "__main__":
    mode = os.environ.get("CHECK_MODE", "check")

    if mode == "daily":
        run_daily()
    else:
        run_check()
