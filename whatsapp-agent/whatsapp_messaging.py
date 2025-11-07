import os
import time
import json
import logging
import pandas as pd
import gspread
import select
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import urllib.parse
import math
from gdrive_attachment_handler import GDriveAttachmentHandler

# Configure the logger - INFO level for cleaner output
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# File logger for detailed debugging
file_handler = logging.FileHandler('/tmp/whatsapp_debug.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('DEBUG|%(message)s|file:%(filename)s:line No.%(lineno)d'))
debug_logger = logging.getLogger('debug')
debug_logger.addHandler(file_handler)
debug_logger.setLevel(logging.DEBUG)

# Suppress verbose logs from underlying libraries
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logging.getLogger('google.auth.transport.requests').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('oauth2client.client').setLevel(logging.WARNING)

load_dotenv()

def calculate_backoff_time(failure_count):
    """Calculate exponential backoff time with max ceiling of 1 hour"""
    if failure_count <= 0:
        return 3  # Base wait time

    wait_times = [30, 120, 600, 1800, 3600]  # 30s, 2m, 10m, 30m, 1h
    index = min(failure_count - 1, len(wait_times) - 1)
    return wait_times[index]

def format_time(seconds):
    """Format seconds into human readable time"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60}s"
    else:
        return f"{seconds//3600}h {(seconds%3600)//60}m"

def get_user_input_with_timeout(prompt, timeout=10):
    """
    Get user input with a timeout. Returns None if timeout expires.
    """
    print(prompt, end='', flush=True)
    
    if sys.platform == 'win32':
        # Windows implementation
        import msvcrt
        start_time = time.time()
        user_input = ''
        
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getch().decode('utf-8')
                if char == '\r':  # Enter key
                    print()  # New line after input
                    return user_input.strip()
                elif char == '\b':  # Backspace
                    if user_input:
                        user_input = user_input[:-1]
                        print('\b \b', end='', flush=True)
                else:
                    user_input += char
                    print(char, end='', flush=True)
            
            if time.time() - start_time > timeout:
                print()  # New line
                return None
            
            time.sleep(0.1)
    else:
        # Unix/Linux/Mac implementation
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            user_input = sys.stdin.readline().strip()
            return user_input
        else:
            print()  # New line
            return None

def attach_files_to_whatsapp(driver, file_paths, send_as_document=False):
    """
    Attach multiple files to WhatsApp message using the attachment button

    Args:
        driver: Selenium WebDriver instance
        file_paths: List of local file paths to attach
        send_as_document: If True, send images as documents (uncompressed). If False, send as photos (compressed)
    """
    try:
        debug_logger.debug(f"  -> Attaching {len(file_paths)} file(s)... (as {'documents' if send_as_document else 'photos'})")
        
        # Method 1: Try to find and use the file input directly (most reliable)
        file_input_selectors = [
            '//input[@accept="image/*,video/mp4,video/3gpp,video/quicktime"]',
            '//input[@type="file"][@accept]',
            '//input[@type="file"]',
        ]
        
        # If sending as document, we need different selectors
        if send_as_document:
            file_input_selectors = [
                '//input[@type="file"][not(@accept)]',  # Document input doesn't have accept attribute
                '//input[@type="file"]',
            ]
        
        wait = WebDriverWait(driver, 10)
        file_input = None
        
        # For documents, we need to click the attachment button first, then click "Document"
        if send_as_document:
            debug_logger.debug("  -> Clicking attachment button to access document option...")
            
            # Click the attachment (paperclip) button
            attachment_btn_selectors = [
                '//div[@title="Attach"]',
                '//span[@data-icon="plus"]',
                '//span[@data-icon="clip"]',
                '//span[@data-icon="attach-menu-plus"]',
                '//button[@aria-label="Attach"]',
                '//div[@aria-label="Attach"]',
                '//span[@data-testid="clip"]',
                '//div[contains(@class, "attach")]',
            ]
            
            attachment_btn = None
            for selector in attachment_btn_selectors:
                try:
                    debug_logger.debug(f"  -> Trying attachment button selector: {selector}")
                    attachment_btn = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                    debug_logger.debug(f"  -> Found attachment button with selector: {selector}")
                    break
                except:
                    continue
            
            if not attachment_btn:
                debug_logger.error("  -> Could not find attachment button")
                return False
            
            attachment_btn.click()
            debug_logger.debug("  -> Clicked attachment button")
            time.sleep(1)
            
            # Now click the "Document" option
            document_btn_selectors = [
                '//input[@accept="*"][@type="file"]',  # Document file input
                '//span[@data-icon="document"]',
                '//button[@aria-label="Document"]',
                '//li[@aria-label="Document"]',
                '//span[contains(text(), "Document")]',
            ]
            
            for selector in document_btn_selectors:
                try:
                    debug_logger.debug(f"  -> Trying document button selector: {selector}")
                    
                    # Check if it's an input element (direct file input)
                    if 'input' in selector.lower():
                        file_input = driver.find_element(By.XPATH, selector)
                        debug_logger.debug(f"  -> Found document file input with selector: {selector}")
                        break
                    else:
                        # It's a button, click it
                        doc_btn = driver.find_element(By.XPATH, selector)
                        doc_btn.click()
                        debug_logger.debug(f"  -> Clicked document button")
                        time.sleep(0.5)
                        
                        # Now find the file input
                        file_input = driver.find_element(By.XPATH, '//input[@type="file"]')
                        debug_logger.debug(f"  -> Found file input after clicking document button")
                        break
                except Exception as e:
                    debug_logger.debug(f"  -> Document button selector failed: {selector}")
                    continue
        else:
            # For photos/images, we MUST click attachment button first, then Photos & Videos
            # to avoid accidentally using the sticker input
            file_input = None

            # Always click attachment button first for photos
            if True:  # Always execute this block for photos
                debug_logger.debug("  -> File input not found directly, trying to click attachment button...")
                
                # Click the attachment (paperclip) button
                wait = WebDriverWait(driver, 30)
                
                # Try different selectors for the attachment button
                attachment_btn_selectors = [
                    '//div[@aria-label="Attach"]',
                    '//div[@title="Attach"]',
                    '//span[@data-icon="plus"]',
                    '//span[@data-icon="clip"]',
                    '//span[@data-icon="attach-menu-plus"]',
                    '//button[@aria-label="Attach"]',
                    '//span[@data-testid="clip"]',
                    '//div[contains(@class, "attach")]',
                    '//button[contains(@aria-label, "ttach")]',  # Partial match for "Attach"
                    '//div[contains(@aria-label, "ttach")]',
                    '//span[contains(@data-icon, "clip")]',
                    '//span[contains(@data-icon, "plus")]',
                    '//*[@data-icon="clip"]',
                    '//*[@data-icon="plus"]',
                ]
                
                attachment_btn = None
                for selector in attachment_btn_selectors:
                    try:
                        debug_logger.debug(f"  -> Trying attachment button selector: {selector}")
                        attachment_btn = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                        debug_logger.debug(f"  -> Found attachment button with selector: {selector}")
                        break
                    except Exception as e:
                        debug_logger.debug(f"  -> Attachment button selector failed: {selector}")
                        continue
                
                if not attachment_btn:
                    debug_logger.error("  -> Could not find attachment button")
                    return False
                
                attachment_btn.click()
                debug_logger.debug("  -> Clicked attachment button")
                time.sleep(1)

                # Click on "Photos & Videos" option to ensure we get the right file input (not stickers)
                photo_video_btn_selectors = [
                    '//span[@data-icon="image"]',
                    '//span[@data-icon="photo"]',
                    '//button[@aria-label="Photos & videos"]',
                    '//li[@aria-label="Photos & videos"]',
                    '//input[@accept="image/*,video/mp4,video/3gpp,video/quicktime"]',
                    '//span[contains(text(), "Photos")]',
                ]

                for selector in photo_video_btn_selectors:
                    try:
                        debug_logger.debug(f"  -> Trying Photos & Videos button selector: {selector}")

                        # Check if it's an input element (direct file input)
                        if 'input' in selector.lower():
                            file_input = driver.find_element(By.XPATH, selector)
                            debug_logger.debug(f"  -> Found photo/video file input with selector: {selector}")
                            break
                        else:
                            # It's a button, click it
                            photo_btn = driver.find_element(By.XPATH, selector)
                            photo_btn.click()
                            debug_logger.debug(f"  -> Clicked Photos & Videos button")
                            time.sleep(0.5)

                            # Now find the file input for photos
                            file_input = driver.find_element(By.XPATH, '//input[@accept="image/*,video/mp4,video/3gpp,video/quicktime"]')
                            debug_logger.debug(f"  -> Found file input after clicking Photos & Videos")
                            break
                    except Exception as e:
                        debug_logger.debug(f"  -> Photos & Videos selector failed: {selector}")
                        continue
        
        if not file_input:
            debug_logger.error("  -> Could not find file input element")
            return False
        
        # Send files one at a time (WhatsApp Web doesn't support multiple files at once)
        for i, file_path in enumerate(file_paths):
            # Convert to absolute path if needed
            abs_path = os.path.abspath(file_path) if not os.path.isabs(file_path) else file_path
            debug_logger.debug(f"  -> Attaching file {i+1}/{len(file_paths)}: {abs_path}")
            file_input.send_keys(abs_path)
            time.sleep(1)  # Wait between files
            
            # After first file, need to find file input again for subsequent files
            if i < len(file_paths) - 1:
                time.sleep(1)
                # Find file input again for next file
                for selector in file_input_selectors:
                    try:
                        file_input = driver.find_element(By.XPATH, selector)
                        debug_logger.debug(f"  -> Found file input for next file")
                        break
                    except:
                        continue
        
        debug_logger.debug(f"  -> All files attached successfully, waiting for preview to load...")
        time.sleep(3)
        
        return True
        
    except Exception as e:
        debug_logger.error(f"  -> Failed to attach files: {e}")
        import traceback
        debug_logger.error(f"  -> Traceback: {traceback.format_exc()}")
        return False

def get_google_sheet():
    # Define the scope
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

    # Get the path to the credentials file from the environment variable
    creds_path = os.getenv('GOOGLE_APPSPOT_API_KEY')
    creds_json = None

    # Add credentials to the account
    try:
        with open(creds_path, 'r') as f:
            creds_json = json.load(f)
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    except FileNotFoundError:
        logger.debug(f"Error: credentials.json not found at path: {creds_path}. Please check the GOOGLE_APPSPOT_API_KEY in your .env file.")
        return None
    except Exception as e:
        logger.debug(f"An error occurred: {e}")
        return None

    # Authorize the clientsheet
    client = gspread.authorize(creds)

    # Get the instance of the Spreadsheet
    sheet_url = os.getenv('GOOGLE_SHEET_URL')
    if not sheet_url:
        logger.debug("Error: GOOGLE_SHEET_URL not found in .env file.")
        return None
    
    try:
        sheet = client.open_by_url(sheet_url)
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        logger.debug("Error: Spreadsheet not found. Please check the URL.")
        return None
    except PermissionError:
        if creds_json:
            logger.debug(f"Permission denied. Please share the Google Sheet with the following email: {creds_json['client_email']}")
        else:
            logger.debug("Permission denied. Could not read client_email from credentials file.")
        return None
    except gspread.exceptions.APIError as e:
        logger.debug(f"An API error occurred: {e}")
        return None

def send_followup_messages(worksheet_name, send_col, phone_col, message_col, contact_person_col, last_message_col, last_message_datetime_col, send_col_val, message_send_limit, pause_between_messages=1, testing=False):
    """
    Sends follow-up messages based on the 'IPC Outreach' Google Sheet.
    Supports attachments from Google Drive links in the format:
    Message text Attachments: [url1, url2, url3]
    """
    driver = None
    attachment_handler = None
    try:
        logger.info("📊 Connecting to Google Sheet...")
        debug_logger.debug("Connecting to Google Sheet...")
        sheet = get_google_sheet()
        if not sheet:
            logger.error("❌ Could not connect to Google Sheet. Exiting.")
            return
        
        # Initialize attachment handler
        attachment_handler = GDriveAttachmentHandler(cache_dir="./gdrive_photos")
        debug_logger.debug("Attachment handler initialized with caching enabled")

        worksheet = sheet.worksheet(worksheet_name)
        debug_logger.debug(f"Reading data from '{worksheet_name}' worksheet...")
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Debug: Log what we found
        logger.info(f"📝 Found {len(df)} total rows in worksheet")
        if len(df) > 0 and send_col in df.columns:
            send_col_values = df[send_col].value_counts()
            logger.info(f"📋 '{send_col}' column values: {send_col_values.to_dict()}")
        
        # Get the 1-based index for the 'send' column
        try:
            headers = worksheet.row_values(1)
            send_col_index = headers.index(send_col) + 1
            message_col_index = headers.index(message_col) + 1
            last_message_col_index = headers.index(last_message_col) + 1
            last_message_datetime_col_index = headers.index(last_message_datetime_col) + 1

            # Add retry tracking column if it doesn't exist
            if 'Retry_Count' not in headers:
                retry_col_index = len(headers) + 1
                worksheet.update_cell(1, retry_col_index, 'Retry_Count')
                debug_logger.debug("Added Retry_Count column to worksheet")
            else:
                retry_col_index = headers.index('Retry_Count') + 1

        except ValueError as e:
            debug_logger.debug(f"Error: Column not found in the worksheet - {e}")
            logger.error("❌ ERROR: Required columns not found in worksheet")
            return
        except Exception as e:
            debug_logger.debug(f"An error occurred while finding the column index: {e}")
            logger.error("❌ ERROR: Failed to read worksheet structure")
            return

        # Rate limiting and retry tracking variables
        consecutive_failures = 0
        max_consecutive_failures = 5
        max_retries_per_number = 3
        base_wait_time = 3  # Base wait between messages
        current_wait_time = base_wait_time

        logger.info("🚀 Setting up Chrome browser...")
        debug_logger.debug("Setting up Chrome driver...")
        options = Options()
        # Create a dedicated profile directory for WhatsApp authentication persistence
        script_dir = os.path.dirname(os.path.abspath(__file__))
        profile_dir = os.path.join(script_dir, "chrome_profile_for_whatsapp")
        
        # Create profile directory if it doesn't exist
        os.makedirs(profile_dir, exist_ok=True)

        # Clean up any lock files from previous runs
        import glob
        lock_files = glob.glob(f"{profile_dir}/**/Singleton*", recursive=True)
        for lock_file in lock_files:
            try:
                os.remove(lock_file)
            except:
                pass

        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--remote-debugging-port=9223")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        # Additional stability options
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--page-load-strategy=eager")  # Don't wait for all resources

        # Set timeouts
        options.add_argument("--timeout=60000")  # 60 second timeout

        # Get ChromeDriver path from webdriver-manager
        driver_path = ChromeDriverManager().install()
        
        # Fix webdriver-manager bug: it sometimes returns the wrong file
        # Check if path ends with an incorrect file and fix it
        if 'THIRD_PARTY_NOTICES' in driver_path or 'LICENSE' in driver_path:
            # Get the directory and point to the actual chromedriver executable
            driver_dir = os.path.dirname(driver_path)
            driver_path = os.path.join(driver_dir, 'chromedriver')
            debug_logger.debug(f"Fixed ChromeDriver path to: {driver_path}")
        
        # Make sure the driver is executable
        if os.path.exists(driver_path):
            os.chmod(driver_path, 0o755)
        
        service = ChromeService(driver_path)
        driver = webdriver.Chrome(service=service, options=options)

        logger.info("📋 Checking messages to send...")
        debug_logger.debug("Chrome driver initialized successfully")
        messages_sent_count = 0
        total_processed = 0
        for index, row in df.iterrows():
            # Check limits and circuit breaker
            if message_send_limit != -1 and messages_sent_count >= message_send_limit:
                logger.info(f"📈 Message send limit of {message_send_limit} reached. Stopping.")
                break

            if consecutive_failures >= max_consecutive_failures:
                logger.error(f"🛑 STOPPING: {consecutive_failures} consecutive failures detected")
                debug_logger.debug(f"Circuit breaker triggered after {consecutive_failures} failures")
                break

            send_value = str(row.get(send_col, '')).strip()
            # Check if this row needs processing (accept YES, TRUE, or the configured value)
            send_triggers = [send_col_val.upper(), 'YES', 'TRUE']
            if send_value.upper() in send_triggers or send_value == 'Not a valid WhatsApp number':
                total_processed += 1
                phone_number = str(row.get(phone_col, '')).strip()
                message = str(row.get(message_col, '')).strip()
                contact_person = str(row.get(contact_person_col, '')).strip()

                # Check retry count
                retry_count = 0
                try:
                    retry_value = worksheet.cell(index + 2, retry_col_index).value
                    retry_count = int(retry_value) if retry_value else 0
                except:
                    retry_count = 0

                if retry_count >= max_retries_per_number:
                    debug_logger.debug(f"Skipping {phone_number}: max retries ({max_retries_per_number}) reached")
                    continue

                # Prepare message with name replacement
                first_name = ''
                if contact_person and contact_person.lower() != 'unknown':
                    first_name = contact_person.split()[0].capitalize()

                if first_name:
                    message = message.replace('{first_name}', first_name)
                else:
                    message = message.replace(' {first_name}', '')

                cleaned_number = "".join(filter(str.isdigit, phone_number))
                if not cleaned_number:
                    debug_logger.debug(f"Skipping row {index + 2}: Invalid phone number '{phone_number}'")
                    continue

                # Use number as-is if it starts with country code, otherwise add 91 (India)
                if len(cleaned_number) > 10:
                    full_phone_number = cleaned_number  # Already has country code
                else:
                    full_phone_number = f"91{cleaned_number}"  # Add India code for legacy compatibility
                logger.info(f"📱 Sending to +{full_phone_number} ({total_processed}/{len(df)}, retry {retry_count+1}/{max_retries_per_number})")

                # Attempt to send message
                success = False
                error_message = ""

                try:
                    # Parse message for attachments
                    clean_message, attachment_urls = attachment_handler.parse_attachments_from_message(message)
                    
                    if attachment_urls:
                        debug_logger.debug(f"  -> Found {len(attachment_urls)} attachment(s) in message")
                    
                    # Open chat
                    url = f"https://web.whatsapp.com/send?phone={full_phone_number}"
                    driver.get(url)
                    debug_logger.debug(f"  -> Opened WhatsApp chat URL: {url}")

                    # Wait for text input - this ensures the chat is fully loaded
                    wait = WebDriverWait(driver, 45)  # Increased timeout for QR code scan if needed
                    
                    # Try multiple selectors for the text input field (WhatsApp changes these frequently)
                    text_input_selectors = [
                        '/html/body/div[1]/div/div[1]/div[3]/div/div[4]/div/footer/div[1]/div/span/div/div[2]/div/div[3]/div/p',
                        '//div[@contenteditable="true"][@data-tab="10"]',
                        '//div[@contenteditable="true"][@role="textbox"]',
                        '//div[@title="Type a message"]',
                        '//div[contains(@class, "copyable-text")][@contenteditable="true"]',
                        '//*[@id="main"]/footer//div[@contenteditable="true"]',
                    ]
                    
                    text_input = None
                    for selector in text_input_selectors:
                        try:
                            debug_logger.debug(f"  -> Trying text input selector: {selector}")
                            text_input = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                            debug_logger.debug(f"  -> Found text input with selector: {selector}")
                            break
                        except Exception as e:
                            debug_logger.debug(f"  -> Text input selector failed: {selector[:50]}...")
                            continue
                    
                    if not text_input:
                        # Check if we're on the QR code page
                        try:
                            qr_code = driver.find_element(By.XPATH, '//canvas[@aria-label="Scan this QR code to link a device!"]')
                            error_message = "WhatsApp Web not logged in. Please scan QR code!"
                            debug_logger.error(f"  -> {error_message}")
                            raise Exception(error_message)
                        except:
                            pass
                        
                        error_message = "Could not find text input field. WhatsApp Web page structure may have changed."
                        debug_logger.error(f"  -> {error_message}")
                        raise TimeoutException(error_message)
                    
                    debug_logger.debug("  -> Chat opened and text input found")
                    time.sleep(2)  # Extra wait to ensure chat is fully loaded
                    
                    # Handle attachments if present
                    if attachment_urls:
                        debug_logger.debug("  -> Downloading attachments from Google Drive...")
                        downloaded_files = attachment_handler.download_multiple(attachment_urls)

                        if downloaded_files:
                            debug_logger.debug(f"  -> Successfully downloaded {len(downloaded_files)} file(s)")

                            # Attach ALL files at once to send as album
                            file_paths_str = [str(f) for f in downloaded_files]
                            if not attach_files_to_whatsapp(driver, file_paths_str, send_as_document=False):
                                debug_logger.error("  -> Failed to attach files, will continue to send text...")
                            else:
                                debug_logger.debug(f"  -> All {len(downloaded_files)} photos attached, waiting for preview...")
                                time.sleep(3)

                                # Send all photos together as album (one click)
                                debug_logger.debug("  -> Sending all photos together as album...")
                                send_button_selectors = [
                                    '//span[@data-icon="send"]',
                                    '//span[@data-icon="wds-ic-send-filled"]',
                                    '//button[@aria-label="Send"]',
                                    '//div[@role="button"][@aria-label="Send"]',
                                ]

                                sent = False
                                for selector in send_button_selectors:
                                    try:
                                        send_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, selector)))
                                        send_btn.click()
                                        debug_logger.debug(f"  -> All {len(downloaded_files)} photos sent together as album")
                                        sent = True
                                        time.sleep(3)
                                        break
                                    except:
                                        continue

                                if not sent:
                                    debug_logger.error("  -> Failed to send photos")

                            debug_logger.debug("  -> Photos sent, now will send text message")

                            # After sending all files, need to find text input again (DOM changed)
                            time.sleep(2)
                            text_input_selectors = [
                                '//div[@contenteditable="true"][@data-tab="10"]',
                                '//div[@contenteditable="true"][@role="textbox"]',
                                '//div[@title="Type a message"]',
                                '//div[contains(@class, "copyable-text")][@contenteditable="true"]',
                                '//*[@id="main"]/footer//div[@contenteditable="true"]',
                            ]

                            text_input = None
                            for selector in text_input_selectors:
                                try:
                                    text_input = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, selector)))
                                    debug_logger.debug(f"  -> Found text input for message: {selector}")
                                    break
                                except:
                                    continue

                            if not text_input:
                                debug_logger.warning("  -> Could not find text input after sending files")
                        else:
                            debug_logger.warning("  -> No files downloaded, sending text only")

                    # Type message (use clean_message without attachment URLs)
                    if text_input:
                        debug_logger.debug(f"  -> Typing message: {clean_message[:100]}...")
                        
                        # Use JavaScript to set the text instead of clicking (avoids click interception issues)
                        try:
                            # Try JavaScript first for reliability
                            driver.execute_script("arguments[0].focus();", text_input)
                            time.sleep(0.3)
                            
                            lines = clean_message.split('\n')
                            for i, line in enumerate(lines):
                                text_input.send_keys(line)
                                if i < len(lines) - 1:
                                    ActionChains(driver).key_down(Keys.SHIFT).key_down(Keys.ENTER).key_up(Keys.ENTER).key_up(Keys.SHIFT).perform()
                            
                            debug_logger.debug("  -> Message typed successfully")
                        except Exception as e:
                            debug_logger.error(f"  -> Failed to type message: {e}")
                    else:
                        debug_logger.error("  -> No text input field available")

                    time.sleep(1)

                    # Send message (skip testing prompts for automation)
                    if not testing:
                        debug_logger.debug("  -> Looking for send button to send text message...")

                        # Try to find and click the send button
                        send_button_selectors = [
                            '//span[@data-icon="send"]',
                            '//span[@data-icon="wds-ic-send-filled"]',
                            '//button[@aria-label="Send"]',
                            '//span[@data-testid="send"]',
                            '//div[@role="button"][@aria-label="Send"]',
                        ]

                        send_button_found = False
                        for selector in send_button_selectors:
                            try:
                                debug_logger.debug(f"  -> Trying send button selector: {selector}")
                                send_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, selector)))
                                send_button.click()
                                debug_logger.debug(f"  -> Text message sent with button: {selector}")
                                send_button_found = True
                                break
                            except Exception as e:
                                debug_logger.debug(f"  -> Send button selector failed: {selector}")
                                continue

                        if not send_button_found:
                            # Fallback to pressing RETURN
                            debug_logger.debug("  -> Send button not found, trying RETURN key...")
                            if text_input:
                                text_input.send_keys(Keys.RETURN)
                                debug_logger.debug("  -> Text message sent with RETURN key")
                            else:
                                debug_logger.error("  -> Could not send text - no send button or text input found")

                        # Wait longer to ensure message is sent before closing browser
                        time.sleep(3)
                        debug_logger.debug("  -> Message sent successfully")

                        # Update success
                        messages_sent_count += 1
                        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        worksheet.update_cell(index + 2, send_col_index, 'Sent')
                        # Save clean message without attachment URLs
                        worksheet.update_cell(index + 2, last_message_col_index, clean_message)
                        worksheet.update_cell(index + 2, last_message_datetime_col_index, current_time)
                        worksheet.update_cell(index + 2, retry_col_index, 0)  # Reset retry count on success

                        logger.info(f"✅ SUCCESS: +{full_phone_number}")
                        consecutive_failures = 0  # Reset failure counter
                        current_wait_time = base_wait_time  # Reset wait time
                        success = True

                except TimeoutException as e:
                    error_message = "Timeout - may not be valid WhatsApp number"
                    debug_logger.debug(f"TimeoutException for +{full_phone_number}: {e}")
                except Exception as e:
                    # Check for specific rate limiting errors
                    error_str = str(e).lower()
                    if "read timed out" in error_str or "connection" in error_str:
                        error_message = "Connection timeout"
                    else:
                        error_message = f"Error: {str(e)[:50]}..."
                    debug_logger.debug(f"Exception for +{full_phone_number}: {e}")

                # Handle failure
                if not success:
                    consecutive_failures += 1
                    retry_count += 1

                    # Update retry count in sheet
                    worksheet.update_cell(index + 2, retry_col_index, retry_count)

                    if retry_count >= max_retries_per_number:
                        worksheet.update_cell(index + 2, send_col_index, f'Failed - {error_message}')
                        logger.error(f"❌ FAILED: +{full_phone_number} - {error_message} (gave up after {max_retries_per_number} tries)")
                    else:
                        worksheet.update_cell(index + 2, send_col_index, send_col_val)  # Keep for retry
                        logger.warning(f"⚠️  RETRY {retry_count}/{max_retries_per_number}: +{full_phone_number} - {error_message}")

                    # Apply exponential backoff
                    backoff_time = calculate_backoff_time(consecutive_failures)
                    if backoff_time > base_wait_time:
                        logger.info(f"⏳ RATE LIMIT: Waiting {format_time(backoff_time)} due to {consecutive_failures} consecutive failures...")
                        time.sleep(backoff_time)
                    else:
                        time.sleep(current_wait_time)

                elif success:
                    # Normal pause between successful messages
                    time.sleep(current_wait_time)

        # Final summary
        logger.info(f"🏁 COMPLETED: {messages_sent_count} messages sent, {total_processed} total processed")
        if consecutive_failures >= max_consecutive_failures:
            logger.error(f"⚠️  Stopped due to circuit breaker ({consecutive_failures} consecutive failures)")

    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"❌ ERROR: Worksheet '{worksheet_name}' not found")
    except KeyboardInterrupt:
        logger.info("🛑 Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}")
        debug_logger.debug(f"Critical error details: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("🔒 Chrome browser closed")
            except:
                debug_logger.debug("Error closing Chrome driver")