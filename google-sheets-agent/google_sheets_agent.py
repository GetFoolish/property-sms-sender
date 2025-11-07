import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from dotenv import load_dotenv
import os
import json

load_dotenv()

__all__ = ['get_google_sheet']

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
        print(f"Error: credentials.json not found at path: {creds_path}. Please check the GOOGLE_APPSPOT_API_KEY in your .env file.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    # Authorize the clientsheet
    client = gspread.authorize(creds)

    # Get the instance of the Spreadsheet
    sheet_url = os.getenv('GOOGLE_SHEET_URL')
    if not sheet_url:
        print("Error: GOOGLE_SHEET_URL not found in .env file.")
        return None
    
    try:
        sheet = client.open_by_url(sheet_url)
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        print("Error: Spreadsheet not found. Please check the URL.")
        return None
    except PermissionError:
        if creds_json:
            print(f"Permission denied. Please share the Google Sheet with the following email: {creds_json['client_email']}")
        else:
            print("Permission denied. Could not read client_email from credentials file.")
        return None
    except gspread.exceptions.APIError as e:
        print(f"An API error occurred: {e}")
        return None


if __name__ == '__main__':
    sheet = get_google_sheet()
    if sheet:
        # Get the first sheet of the Spreadsheet
        sheet_instance = sheet.get_worksheet(0)
        # Get all the records of the data
        records_data = sheet_instance.get_all_records()
        # Convert the data into a pandas dataframe
        records_df = pd.DataFrame.from_dict(records_data)
        # Print the first row
        print(records_df.head(1))
