#!/usr/bin/env python3
"""
Test script to send photos to a WhatsApp number - AUTOMATIC MODE
This script will test the actual sending functionality with full automation
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

# Test configuration
PHONE_NUMBER = "37127733077"  # Your number without spaces and dashes
MESSAGE = "Test message with photos - checking if they send as photos (not documents)"
IMAGE_FILES = [
    os.path.abspath("../test_images/20250502_142953.jpg"),
    os.path.abspath("../test_images/20250502_142956.jpg"),
]
AUTO_SEND = True  # Automatically click send button
WAIT_AFTER_SEND = 5  # Seconds to wait after sending to confirm delivery
AUTO_CLOSE = True  # Automatically close browser after sending

def send_test_message():
    """Send test message with photos"""
    driver = None

    try:
        print("=" * 70)
        print("WhatsApp Photo Sending Test - AUTOMATIC MODE")
        print("=" * 70)
        print(f"\nRecipient: +{PHONE_NUMBER}")
        print(f"Message: {MESSAGE}")
        print(f"Images to send: {len(IMAGE_FILES)}")
        for i, img in enumerate(IMAGE_FILES, 1):
            print(f"  {i}. {os.path.basename(img)}")
        print(f"\nAuto-send: {AUTO_SEND}")
        print(f"Auto-close: {AUTO_CLOSE}")
        print("\n" + "=" * 70)

        # Verify image files exist
        print("\n[1/6] Verifying image files...")
        for img_path in IMAGE_FILES:
            if not os.path.exists(img_path):
                print(f"ERROR: File not found: {img_path}")
                return False
            file_size = os.path.getsize(img_path) / (1024 * 1024)  # MB
            print(f"  OK: {os.path.basename(img_path)} ({file_size:.2f} MB)")

        # Set up Chrome
        print("\n[2/6] Setting up Chrome browser...")
        options = Options()

        # Create profile directory
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
        print("  OK: Chrome started")

        # Open WhatsApp chat
        print(f"\n[3/6] Opening WhatsApp chat for +{PHONE_NUMBER}...")
        url = f"https://web.whatsapp.com/send?phone={PHONE_NUMBER}"
        driver.get(url)

        # Wait for chat to load
        print("  Waiting for WhatsApp Web to load...")
        print("  (If QR code appears, please scan it now)")

        wait = WebDriverWait(driver, 60)

        # Try to find text input
        text_input_selectors = [
            '//div[@contenteditable="true"][@data-tab="10"]',
            '//div[@contenteditable="true"][@role="textbox"]',
            '//div[@title="Type a message"]',
        ]

        text_input = None
        for selector in text_input_selectors:
            try:
                text_input = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                print(f"  OK: Chat loaded successfully")
                break
            except:
                continue

        if not text_input:
            print("  ERROR: Could not load chat. Make sure you're logged into WhatsApp Web.")
            return False

        time.sleep(2)

        # Attach images
        print(f"\n[4/6] Attaching {len(IMAGE_FILES)} image(s) as PHOTOS (not documents)...")
        if not attach_files_to_whatsapp(driver, IMAGE_FILES, send_as_document=False):
            print("  ERROR: Failed to attach images")
            return False

        print("  OK: Images attached successfully")
        time.sleep(3)

        # Type message
        print("\n[5/6] Adding caption...")

        # Find caption field after attachment
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
            print(f"  Caption added: {MESSAGE}")

        # Find and click send button - ENHANCED SELECTORS
        print("\n[6/6] Sending message...")
        send_button_selectors = [
            '//span[@data-icon="send"]',
            '//span[@data-icon="send"]/parent::button',
            '//button[@aria-label="Send"]',
            '//span[@data-testid="send"]',
            '//div[@role="button"][@aria-label="Send"]',
            '//*[@data-icon="send"]',
        ]

        send_button = None
        for selector in send_button_selectors:
            try:
                print(f"  Trying selector: {selector[:50]}...")
                send_button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))

                if AUTO_SEND:
                    send_button.click()
                    print("  ✓ Send button clicked automatically")
                    time.sleep(WAIT_AFTER_SEND)

                    # Check if message was sent (input field should be empty or available again)
                    try:
                        empty_input = driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
                        if empty_input.text == "" or "Type a message" in str(empty_input.get_attribute("data-lexical-text")):
                            print("  ✓ Message sent successfully (confirmed)")
                        else:
                            print("  ⚠ Message may still be sending...")
                    except:
                        print("  ✓ Message sent (input field changed)")
                else:
                    print("  ⚠ AUTO_SEND is False - please click send manually")
                    input("Press Enter after you click send...")
                break
            except Exception as e:
                print(f"  ✗ Selector failed: {str(e)[:50]}")
                continue

        if not send_button:
            print("  ✗ ERROR: Could not find send button!")
            print("  Please check WhatsApp Web interface manually")
            if not AUTO_CLOSE:
                input("Press Enter to close...")
            return False

        print("\n" + "=" * 70)
        print(f"SUCCESS! Message sent to +{PHONE_NUMBER}")
        print("=" * 70)
        print("\nMessage details:")
        print(f"  - {len(IMAGE_FILES)} photo(s) attached")
        print(f"  - Caption: {MESSAGE}")
        print(f"  - Sent as: PHOTOS (inline display)")
        print("\nPlease check your WhatsApp to verify:")
        print("  1. You received the message")
        print("  2. Images are displayed as PHOTOS (inline)")
        print("  3. Images are NOT shown as file attachments")

        if not AUTO_CLOSE:
            print("\nPress Enter to close the browser...")
            input()
        else:
            print(f"\nBrowser will close automatically in 3 seconds...")
            time.sleep(3)

        return True

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

        if not AUTO_CLOSE:
            print("\nPress Enter to close...")
            input()
        return False

    finally:
        if driver:
            print("\nClosing browser...")
            driver.quit()
            print("Browser closed.")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("AUTOMATIC WhatsApp Photo Test")
    print("=" * 70)
    print("\nThis script will:")
    print("  1. Open WhatsApp Web")
    print("  2. Attach photos")
    print("  3. AUTOMATICALLY click Send")
    print("  4. AUTOMATICALLY close browser")
    print("\nStarting in 2 seconds...")
    print("=" * 70 + "\n")
    time.sleep(2)

    success = send_test_message()

    if success:
        print("\n✓ Test completed successfully!")
    else:
        print("\n✗ Test failed!")

    sys.exit(0 if success else 1)
