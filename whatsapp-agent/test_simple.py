#!/usr/bin/env python3
"""
Simple WhatsApp Photo Test - ASCII only, no emoji
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from whatsapp_messaging import attach_files_to_whatsapp

# Configuration
PHONE_NUMBER = "37127733077"
MESSAGE = "Test message with photos"
IMAGE_FILES = [
    os.path.abspath("../test_images/20250502_142953.jpg"),
    os.path.abspath("../test_images/20250502_142956.jpg"),
]

def send_test():
    driver = None

    try:
        print("\n" + "="*70)
        print("WhatsApp Photo Test - Simple Version")
        print("="*70)
        print(f"\nPhone: +{PHONE_NUMBER}")
        print(f"Message: {MESSAGE}")
        print(f"Images: {len(IMAGE_FILES)}")
        print("\n" + "="*70)

        # Verify files
        print("\n[1/5] Checking images...")
        for img in IMAGE_FILES:
            if not os.path.exists(img):
                print(f"ERROR: File not found: {img}")
                return False
            size_mb = os.path.getsize(img) / (1024 * 1024)
            print(f"  OK: {os.path.basename(img)} ({size_mb:.2f} MB)")

        # Setup Chrome
        print("\n[2/5] Starting Chrome...")
        options = Options()

        script_dir = os.path.dirname(os.path.abspath(__file__))
        profile_dir = os.path.join(script_dir, "chrome_profile_for_whatsapp")
        os.makedirs(profile_dir, exist_ok=True)

        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument("--remote-debugging-port=9223")

        driver_path = ChromeDriverManager().install()
        if 'THIRD_PARTY_NOTICES' in driver_path or 'LICENSE' in driver_path:
            driver_dir = os.path.dirname(driver_path)
            driver_path = os.path.join(driver_dir, 'chromedriver')

        if os.path.exists(driver_path):
            os.chmod(driver_path, 0o755)

        service = ChromeService(driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        print("  Chrome started")

        # Open chat
        print(f"\n[3/5] Opening chat +{PHONE_NUMBER}...")
        url = f"https://web.whatsapp.com/send?phone={PHONE_NUMBER}"
        driver.get(url)

        print("  Waiting for WhatsApp... (scan QR if needed)")
        wait = WebDriverWait(driver, 60)

        text_input_selectors = [
            '//div[@contenteditable="true"][@data-tab="10"]',
            '//div[@contenteditable="true"][@role="textbox"]',
            '//div[@title="Type a message"]',
        ]

        text_input = None
        for selector in text_input_selectors:
            try:
                text_input = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                print("  Chat loaded")
                break
            except:
                continue

        if not text_input:
            print("  ERROR: Could not load chat")
            return False

        time.sleep(2)

        # Attach images
        print(f"\n[4/5] Attaching {len(IMAGE_FILES)} photos...")
        if not attach_files_to_whatsapp(driver, IMAGE_FILES, send_as_document=False):
            print("  ERROR: Failed to attach")
            return False

        print("  Images attached")
        time.sleep(3)

        # Add caption
        print("\n[5/5] Adding caption and sending...")
        caption_selectors = [
            '//div[@contenteditable="true"][@data-tab="10"]',
            '//div[@contenteditable="true"][@role="textbox"]',
        ]

        caption_input = None
        for selector in caption_selectors:
            try:
                caption_input = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                break
            except:
                continue

        if caption_input:
            driver.execute_script("arguments[0].focus();", caption_input)
            time.sleep(0.5)
            caption_input.send_keys(MESSAGE)
            print(f"  Caption: {MESSAGE}")

        # Send
        send_button_selectors = [
            '//span[@data-icon="wds-ic-send-filled"]',  # NEW WhatsApp selector
            '//span[@data-icon="send"]',
            '//button[@aria-label="Send"]',
            '//span[@data-testid="send"]',
            '//div[@role="button"][@aria-label="Send"]',
        ]

        send_button = None
        longer_wait = WebDriverWait(driver, 15)  # Longer timeout for send button
        for selector in send_button_selectors:
            try:
                send_button = longer_wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                send_button.click()
                print("  Send clicked")
                break
            except:
                print(f"  Trying next selector...")
                continue

        if not send_button:
            print("  WARNING: Send button not found")
            input("Press Enter after manual send...")

        time.sleep(3)

        print("\n" + "="*70)
        print("SUCCESS!")
        print("="*70)
        print("\nCheck your WhatsApp:")
        print("  1. Message received")
        print("  2. Images display inline")
        print("  3. NOT as file attachments")
        print("\nBrowser will close in 3 seconds...")
        time.sleep(3)

        return True

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to close...")
        return False

    finally:
        if driver:
            print("\nClosing browser...")
            driver.quit()


if __name__ == "__main__":
    print("\nStarting in 2 seconds...")
    time.sleep(2)

    success = send_test()

    if success:
        print("\nTest completed successfully!")
        sys.exit(0)
    else:
        print("\nTest failed!")
        sys.exit(1)
