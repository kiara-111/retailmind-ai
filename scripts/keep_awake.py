"""Opens the app in a real browser so Streamlit Community Cloud does not put it to sleep.

If the app is already asleep, it clicks the wake-up button and waits until the app is back.
Run by .github/workflows/keep-awake.yml.
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "").strip()


def main() -> int:
    if not URL.startswith("http"):
        print("APP_URL is not set (GitHub: Settings > Secrets and variables > Actions > Variables).")
        return 1
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(8_000)
        wake = page.get_by_role("button", name="Yes, get this app back up!")
        if wake.count():
            print("App was asleep, waking it up.")
            wake.first.click()
            page.wait_for_timeout(90_000)
        else:
            print("App is awake.")
        print("Page title:", page.title())
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
