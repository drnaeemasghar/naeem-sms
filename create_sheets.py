import gspread
from google.oauth2.service_account import Credentials

def create_sheets():
    # Define the scope
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

    # Load credentials from file
    credentials = Credentials.from_service_account_file('credentials.json', scopes=scope)
    client = gspread.authorize(credentials)

    # Use the existing spreadsheet by ID
    spreadsheet_id = "17txcTfxSItZaeMSaB-gF6_8f50fniyQqbChq9Wdl27k"
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        print(f"Successfully opened existing spreadsheet with ID: {spreadsheet_id}")
    except gspread.exceptions.APIError as e:
        print(f"Error opening spreadsheet: {e}")
        print("Please make sure the spreadsheet exists and is shared with the service account email in your credentials.json file.")
        return None

    # Define required sheets and their columns
    required_sheets = {
        "users": ["id", "pass"],
        "products": ["id", "name", "price", "qr_url"],
        "sold": ["customer_name", "products_and_quantity", "total_price", "discount", "coupon", "final_price", "date"],
        "coupons": ["coupon", "percentage"],
        "login_cookies": ["user_id", "session_id", "expiry"]
    }

    # Get all worksheet titles
    existing_sheets = [worksheet.title for worksheet in spreadsheet.worksheets()]

    # Create missing sheets and set up headers
    for sheet_name, headers in required_sheets.items():
        if sheet_name not in existing_sheets:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
            # Add headers to the first row
            worksheet.update('A1:' + chr(65 + len(headers) - 1) + '1', [headers])
            print(f"Created sheet: {sheet_name} with headers: {headers}")
        else:
            print(f"Sheet {sheet_name} already exists")
            # Check if headers match and update if needed
            worksheet = spreadsheet.worksheet(sheet_name)
            existing_headers = worksheet.row_values(1)
            if existing_headers != headers:
                worksheet.update('A1:' + chr(65 + len(headers) - 1) + '1', [headers])
                print(f"Updated headers for sheet: {sheet_name}")

    print("All required sheets have been created and configured!")
    return spreadsheet_id

if __name__ == "__main__":
    spreadsheet_id = create_sheets()
    if spreadsheet_id:
        print(f"Spreadsheet ID: {spreadsheet_id}")
        print("Please ensure the 'static/qr_codes' folder exists in your project directory.")
        print("You can create it with: mkdir -p static/qr_codes")