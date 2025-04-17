import gspread
from google.oauth2.service_account import Credentials

def add_coupon():
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

    # Access the coupons worksheet
    coupons_sheet = spreadsheet.worksheet("coupons")
    
    # Get all existing coupon codes
    existing_coupons = coupons_sheet.col_values(1)[1:]  # Skip header
    
    # Get new coupon details
    print("=== Add New Coupon ===")
    while True:
        coupon_code = input("Enter coupon code: ").strip().upper()
        if coupon_code in existing_coupons:
            print("Coupon code already exists. Please choose another.")
            continue
        
        while True:
            try:
                percentage = float(input("Enter discount percentage (1-100): "))
                if 0 < percentage <= 100:
                    break
                else:
                    print("Percentage must be between 1 and 100.")
            except ValueError:
                print("Please enter a valid number.")
        
        break
    
    # Add new coupon to the sheet
    next_row = len(existing_coupons) + 2  # +1 for header, +1 for 0-indexing
    coupons_sheet.update_cell(next_row, 1, coupon_code)
    coupons_sheet.update_cell(next_row, 2, percentage)
    
    print(f"Coupon '{coupon_code}' with {percentage}% discount added successfully!")

if __name__ == "__main__":
    add_coupon()
