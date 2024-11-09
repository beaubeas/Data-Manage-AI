from playwright.sync_api import sync_playwright
from playwright.sync_api import sync_playwright
import time  # Correctly import the time module

def run_playwright():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set headless=False to see the browser
        page = browser.new_page()
        page.goto("http://supercog.ai")
        print(page.title())  # Print the title of the page
        time.sleep(60)  # Properly reference the sleep function from the time module
        browser.close()  # Ensure the browser is closed after operation

if __name__ == "__main__":
    run_playwright()
