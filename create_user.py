import gspread
from google.oauth2.service_account import Credentials
import getpass

def create_user():
    # Define the scope
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    # Load credentials from file
    credentials = Credentials.from_service_account_file('credentials.json', scopes=scope)
    client = gspread.authorize(credentials)

    # Open the spreadsheet
    try:
        spreadsheet = client.open("NaeemStoreManagement")
    except gspread.SpreadsheetNotFound:
        print("Spreadsheet not found. Please run create_sheets.py first.")
        return

    # Access the users worksheet
    users_sheet = spreadsheet.worksheet("users")
    
    # Get all existing usernames
    existing_users = users_sheet.col_values(1)[1:]  # Skip header
    
    # Get new user details
    print("=== Create New User ===")
    while True:
        username = input("Enter username: ")
        if username in existing_users:
            print("Username already exists. Please choose another.")
            continue
        
        password = getpass.getpass("Enter password: ")
        confirm_password = getpass.getpass("Confirm password: ")
        
        if password != confirm_password:
            print("Passwords do not match. Please try again.")
            continue
        
        break
    
    # Add new user to the sheet
    next_row = len(existing_users) + 2  # +1 for header, +1 for 0-indexing
    users_sheet.update_cell(next_row, 1, username)
    users_sheet.update_cell(next_row, 2, password)
    
    print(f"User '{username}' created successfully!")

if __name__ == "__main__":
    create_user()
