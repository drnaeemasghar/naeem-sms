from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import gspread
from google.oauth2.service_account import Credentials
import qrcode
from io import BytesIO
import base64
import uuid
import os
import json
import datetime
from werkzeug.utils import secure_filename
import cv2
from pyzbar.pyzbar import decode
import numpy as np
from PIL import Image
import time
import secrets
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Define the scope
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Google Drive folder ID where QR codes will be stored
DRIVE_FOLDER_ID = "1nYyUNMWGpU0SpM5Lwg3F5Jd9ukceVm-p"  # Your Google Drive folder ID

# Local folder for temporary QR code storage
QR_FOLDER = 'static/qr_codes'
if not os.path.exists(QR_FOLDER):
    os.makedirs(QR_FOLDER)

# Initialize Google Sheets client
def get_gspread_client():
    credentials = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    return gspread.authorize(credentials)

# Helper function to get spreadsheet
def get_spreadsheet():
    client = get_gspread_client()
    return client.open_by_key("17txcTfxSItZaeMSaB-gF6_8f50fniyQqbChq9Wdl27k")

# Function to upload file to Google Drive
def upload_to_drive(file_path, file_name, mime_type):
    credentials = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    drive_service = build('drive', 'v3', credentials=credentials)
    
    file_metadata = {
        'name': file_name,
        'parents': [DRIVE_FOLDER_ID]
    }
    
    media = MediaFileUpload(file_path, mimetype=mime_type)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webContentLink'
    ).execute()
    
    # Make the file publicly accessible
    drive_service.permissions().create(
        fileId=file.get('id'),
        body={'type': 'anyone', 'role': 'reader'},
        fields='id'
    ).execute()
    
    return file.get('id'), file.get('webContentLink')

# Check if user is logged in
def is_logged_in():
    return 'user_id' in session

# Login required decorator
def login_required(f):
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def index():
    # Check if any users exist
    spreadsheet = get_spreadsheet()
    users_sheet = spreadsheet.worksheet("users")
    all_users = users_sheet.get_all_values()
    
    if len(all_users) <= 1:  # Only header row exists
        return redirect(url_for('setup'))
    
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    spreadsheet = get_spreadsheet()
    users_sheet = spreadsheet.worksheet("users")
    
    # Check if any users exist
    all_users = users_sheet.get_all_values()
    if len(all_users) > 1:  # Header row + at least one user
        flash('Setup already completed. Users already exist.', 'info')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('setup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('setup.html')
        
        # Add user to sheet
        users_sheet.append_row([username, password])
        
        flash('Setup completed! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Validate credentials against Google Sheet
        spreadsheet = get_spreadsheet()
        users_sheet = spreadsheet.worksheet("users")
        
        # Find user
        try:
            # Get all users and check if username exists
            all_users = users_sheet.get_all_values()
            user_found = False
            
            # Skip header row
            for i, row_data in enumerate(all_users[1:], start=2):
                if row_data and row_data[0] == username:
                    user_found = True
                    row = i
                    stored_password = row_data[1]
                    break
            
            if not user_found:
                flash('User not found', 'error')
                return render_template('login.html')
            
            if password == stored_password:
                # Set session
                session['user_id'] = username
                session['logged_in'] = True
                
                # Store session in Google Sheet for persistence
                cookies_sheet = spreadsheet.worksheet("login_cookies")
                session_id = str(uuid.uuid4())
                expiry = (datetime.datetime.now() + datetime.timedelta(days=7)).isoformat()
                
                cookies_sheet.append_row([username, session_id, expiry])
                session['session_id'] = session_id
                
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid password', 'error')
        except Exception as e:
            print(f"Login error: {e}")
            flash('An error occurred during login', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session and 'session_id' in session:
        # Remove session from Google Sheet
        try:
            spreadsheet = get_spreadsheet()
            cookies_sheet = spreadsheet.worksheet("login_cookies")
            cell = cookies_sheet.find(session['session_id'])
            cookies_sheet.delete_row(cell.row)
        except (gspread.exceptions.CellNotFound, Exception) as e:
            print(f"Error removing session: {e}")
    
    # Clear session
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', username=session.get('user_id', 'User'))

@app.route('/get_stats')
@login_required
def get_stats():
    try:
        spreadsheet = get_spreadsheet()
        
        # Get total products
        products_sheet = spreadsheet.worksheet("products")
        products_rows = products_sheet.get_all_values()
        total_products = len(products_rows) - 1  # Subtract header row
        
        # Get total sales
        sold_sheet = spreadsheet.worksheet("sold")
        sold_rows = sold_sheet.get_all_values()
        
        if len(sold_rows) > 1:
            # Calculate total sales (sum of final_price column)
            total_sales = 0
            today_sales = 0
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            
            for row in sold_rows[1:]:  # Skip header
                if len(row) >= 6:  # Make sure row has enough columns
                    try:
                        final_price = float(row[5])  # final_price is the 6th column (index 5)
                        total_sales += final_price
                        
                        # Check if sale was today
                        if len(row) >= 7 and row[6].startswith(today):
                            today_sales += final_price
                    except (ValueError, TypeError):
                        pass  # Skip if not a valid number
        else:
            total_sales = 0
            today_sales = 0
        
        return jsonify({
            'total_products': total_products,
            'total_sales': total_sales,
            'today_sales': today_sales
        })
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({
            'total_products': 0,
            'total_sales': 0,
            'today_sales': 0
        })

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        
        # Validate input
        if not name or not price:
            flash('Product name and price are required', 'error')
            return redirect(url_for('add_product'))
        
        try:
            price = float(price)
        except ValueError:
            flash('Price must be a number', 'error')
            return redirect(url_for('add_product'))
        
        # Get spreadsheet and worksheet
        spreadsheet = get_spreadsheet()
        products_sheet = spreadsheet.worksheet("products")
        
        # Generate product ID
        all_ids = products_sheet.col_values(1)[1:]  # Skip header
        if all_ids:
            try:
                last_id = max([int(id) for id in all_ids if id.isdigit()])
                product_id = str(last_id + 1)
            except ValueError:
                product_id = "1"
        else:
            product_id = "1"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(product_id)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        qr_filename = f"product_{product_id}.png"
        qr_path = os.path.join(QR_FOLDER, qr_filename)
        img.save(qr_path)
        
        # Upload QR code to Google Drive
        try:
            file_id, web_link = upload_to_drive(qr_path, qr_filename, 'image/png')
            qr_url = web_link
            print(f"Uploaded QR code to Drive: {qr_url}")
        except Exception as e:
            print(f"Error uploading to Drive: {e}")
            qr_url = f"/static/qr_codes/{qr_filename}"  # Fallback to local path
        
        # Save product to Google Sheet
        products_sheet.append_row([product_id, name, price, qr_url])
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('add_product'))
    
    return render_template('add_product.html')

@app.route('/product_list')
@login_required
def product_list():
    # Get all products
    spreadsheet = get_spreadsheet()
    products_sheet = spreadsheet.worksheet("products")
    
    # Get all rows including headers
    all_rows = products_sheet.get_all_values()
    
    # Skip header row
    if len(all_rows) > 1:
        headers = all_rows[0]
        products = [dict(zip(headers, row)) for row in all_rows[1:]]
    else:
        products = []
    
    return render_template('product_list.html', products=products)

@app.route('/search_products')
@login_required
def search_products():
    query = request.args.get('query', '').lower()
    
    # Get all products
    spreadsheet = get_spreadsheet()
    products_sheet = spreadsheet.worksheet("products")
    
    # Get all rows including headers
    all_rows = products_sheet.get_all_values()
    
    # Skip header row and filter based on query
    if len(all_rows) > 1:
        headers = all_rows[0]
        all_products = [dict(zip(headers, row)) for row in all_rows[1:]]
        
        # Filter products based on query
        filtered_products = []
        for product in all_products:
            if (query in product['name'].lower() or 
                query in product['price'].lower()):
                filtered_products.append(product)
    else:
        filtered_products = []
    
    return jsonify(filtered_products)

@app.route('/edit_product/<product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    spreadsheet = get_spreadsheet()
    products_sheet = spreadsheet.worksheet("products")
    
    try:
        # Find product by ID
        cell = products_sheet.find(product_id)
        row = cell.row
        
        if request.method == 'POST':
            name = request.form['name']
            price = request.form['price']
            
            # Validate input
            if not name or not price:
                flash('Product name and price are required', 'error')
                return redirect(url_for('edit_product', product_id=product_id))
            
            try:
                price = float(price)
            except ValueError:
                flash('Price must be a number', 'error')
                return redirect(url_for('edit_product', product_id=product_id))
            
            # Update product
            products_sheet.update_cell(row, 2, name)  # Update name
            products_sheet.update_cell(row, 3, price)  # Update price
            
            flash('Product updated successfully!', 'success')
            return redirect(url_for('product_list'))
        
        # Get product data for display
        product = {
            'id': products_sheet.cell(row, 1).value,
            'name': products_sheet.cell(row, 2).value,
            'price': products_sheet.cell(row, 3).value,
            'qr_url': products_sheet.cell(row, 4).value
        }
        
        return render_template('edit_product.html', product=product)
    
    except gspread.exceptions.CellNotFound:
        flash('Product not found', 'error')
        return redirect(url_for('product_list'))

@app.route('/delete_product/<product_id>')
@login_required
def delete_product(product_id):
    spreadsheet = get_spreadsheet()
    products_sheet = spreadsheet.worksheet("products")
    
    try:
        # Find product by ID
        cell = products_sheet.find(product_id)
        row = cell.row
        
        # Get QR URL before deleting
        qr_url = products_sheet.cell(row, 4).value
        
        # Delete product
        products_sheet.delete_row(row)
        
        # Delete QR code file if it exists locally
        qr_filename = f"product_{product_id}.png"
        qr_path = os.path.join(QR_FOLDER, qr_filename)
        if os.path.exists(qr_path):
            os.remove(qr_path)
        
        flash('Product deleted successfully!', 'success')
    except gspread.exceptions.CellNotFound:
        flash('Product not found', 'error')
    
    return redirect(url_for('product_list'))

@app.route('/main')
@login_required
def main_page():
    return render_template('main_page.html')

@app.route('/get_product/<product_id>')
@login_required
def get_product(product_id):
    spreadsheet = get_spreadsheet()
    products_sheet = spreadsheet.worksheet("products")
    
    try:
        # Find product by ID
        cell = products_sheet.find(product_id)
        row = cell.row
        
        product = {
            'id': products_sheet.cell(row, 1).value,
            'name': products_sheet.cell(row, 2).value,
            'price': products_sheet.cell(row, 3).value,
            'qr_url': products_sheet.cell(row, 4).value
        }
        
        return jsonify({'success': True, 'product': product})
    except gspread.exceptions.CellNotFound:
        return jsonify({'success': False, 'message': 'Product not found'})

@app.route('/check_coupon/<coupon_code>')
@login_required
def check_coupon(coupon_code):
    spreadsheet = get_spreadsheet()
    coupons_sheet = spreadsheet.worksheet("coupons")
    
    try:
        # Find coupon by code
        cell = coupons_sheet.find(coupon_code.upper())
        row = cell.row
        
        percentage = coupons_sheet.cell(row, 2).value
        
        return jsonify({
            'success': True, 
            'coupon': coupon_code.upper(), 
            'percentage': float(percentage)
        })
    except gspread.exceptions.CellNotFound:
        return jsonify({'success': False, 'message': 'Coupon not found'})

@app.route('/complete_sale', methods=['POST'])
@login_required
def complete_sale():
    data = request.json
    
    customer_name = data.get('customer_name', 'Guest')
    products_data = data.get('products', [])
    total_price = data.get('total_price', 0)
    discount = data.get('discount', 0)
    coupon = data.get('coupon', '')
    final_price = data.get('final_price', 0)
    
    # Format products and quantity
    products_and_quantity = []
    for product in products_data:
        products_and_quantity.append(f"{product['name']} x{product['quantity']}")
    
    products_and_quantity_str = ", ".join(products_and_quantity)
    
    # Save to sold sheet
    spreadsheet = get_spreadsheet()
    sold_sheet = spreadsheet.worksheet("sold")
    
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sold_sheet.append_row([
        customer_name,
        products_and_quantity_str,
        total_price,
        discount,
        coupon,
        final_price,
        current_date
    ])
    
    return jsonify({'success': True, 'message': 'Sale completed successfully!'})

@app.route('/print_receipt')
@login_required
def print_receipt():
    # Get data from query parameters
    customer_name = request.args.get('customer_name', 'Guest')
    products_json = request.args.get('products', '[]')
    total_price = request.args.get('total_price', '0')
    discount = request.args.get('discount', '0')
    coupon = request.args.get('coupon', '')
    final_price = request.args.get('final_price', '0')
    
    # Parse products JSON
    try:
        products = json.loads(products_json)
    except json.JSONDecodeError:
        products = []
    
    # Format date
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return render_template(
        'print_receipt.html',
        customer_name=customer_name,
        products=products,
        total_price=total_price,
        discount=discount,
        coupon=coupon,
        final_price=final_price,
        date=current_date
    )

if __name__ == '__main__':
    app.run(debug=True)