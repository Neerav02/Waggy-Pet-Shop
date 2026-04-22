import gevent.monkey
gevent.monkey.patch_all()

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, Response
from flask_pymongo import PyMongo
from bson import ObjectId
import bcrypt
import os
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta
from functools import wraps
import logging
import re
from PIL import Image
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import requests
from urllib.parse import quote
from flask_mail import Mail, Message
import secrets
import jwt
import io
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import WebApplicationClient
from pymongo import MongoClient
from dotenv import load_dotenv
from groq import Groq
import stripe
from flask_socketio import SocketIO, emit, join_room
import socket

# Patch for Windows hostname SMTP HELO rejection
socket.getfqdn = lambda *args: 'localhost'

# ============================================================
# CONFIGURATION
# ============================================================
load_dotenv()
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# --- Core Config ---
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# --- MongoDB ---
ATLAS_URI = os.environ.get("MONGO_URI")
if not ATLAS_URI:
    raise ValueError("No MONGO_URI found in environment variables")
app.config["MONGO_URI"] = ATLAS_URI
mongo = PyMongo(app, connect=False)

@app.before_first_request
def setup_database():
    try:
        mongo.db.command('ping')
        logger.info("Successfully connected to MongoDB Atlas!")
        mongo.db.users.create_index("email", unique=True)
        mongo.db.users.create_index("username", unique=True)
        mongo.db.products.create_index("name")
        mongo.db.orders.create_index("user_id")
        mongo.db.cart.create_index("user_id", unique=True)
        mongo.db.delivery_locations.create_index([("coordinates", "2dsphere")])
        logger.info("Database indexes created successfully!")
    except Exception as e:
        logger.error(f"MongoDB Atlas connection error: {str(e)}")

# --- Google OAuth ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = os.environ.get("GOOGLE_DISCOVERY_URL", "https://accounts.google.com/.well-known/openid-configuration")
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# --- Admin ---
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "WaggyAdmin@2026Secure")

# --- Google Places ---
GOOGLE_PLACES_API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY', '')

# --- Email / Mail ---
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', '')
mail = Mail(app)

# --- Uploads ---
app.config['UPLOAD_FOLDER'] = 'static/images'

# --- Groq AI ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# --- Stripe Payments ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# --- SocketIO ---
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# --- Location / Geopy ---
geolocator = Nominatim(user_agent="waggy_pet_shop", timeout=10)


# ============================================================
# DECORATORS
# ============================================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def location_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            if 'selected_location' not in session:
                flash('Please select your delivery location first', 'warning')
                return redirect(url_for('select_location', next=request.url))
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Location middleware error: {str(e)}")
            flash('Location error occurred. Please try again.', 'danger')
            return redirect(url_for('select_location'))
    return decorated_function


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_username():
    if 'user_id' in session:
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        return user['username'] if user else None
    return None

def get_cart_count():
    if 'user_id' in session:
        cart = mongo.db.cart.find_one({'user_id': session['user_id']})
        return len(cart['items']) if cart and 'items' in cart else 0
    elif 'guest_cart' in session:
        return len(session['guest_cart'])
    return 0


# ============================================================
# CONTEXT PROCESSORS
# ============================================================
@app.context_processor
def inject_location():
    try:
        selected_location = session.get('selected_location')
        return dict(
            current_location=selected_location if selected_location else None,
            is_location_set='selected_location' in session
        )
    except Exception as e:
        logger.error(f"Location injection error: {str(e)}")
        return dict(current_location=None, is_location_set=False)

@app.template_filter('usd_to_inr')
def usd_to_inr(amount):
    """Convert USD to INR"""
    return "₹{:.2f}".format(float(amount) * 75)


# ============================================================
# LOCATION ROUTES
# ============================================================
@app.route('/api/locations/search')
def search_locations():
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify([])
        if GOOGLE_PLACES_API_KEY:
            url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
            params = {
                'input': query,
                'key': GOOGLE_PLACES_API_KEY,
                'components': 'country:in',
                'types': 'address'
            }
            response = requests.get(url, params=params)
            data = response.json()
            if data.get('status') == 'OK':
                predictions = []
                for prediction in data.get('predictions', []):
                    predictions.append({
                        'description': prediction['description'],
                        'place_id': prediction['place_id'],
                        'structured_formatting': prediction.get('structured_formatting', {})
                    })
                return jsonify(predictions)
        return jsonify([])
    except Exception as e:
        logger.error(f"Location search error: {str(e)}")
        return jsonify([])

@app.route('/api/locations/details')
def get_location_details():
    try:
        place_id = request.args.get('place_id')
        if not place_id:
            return jsonify({'error': 'Place ID is required'}), 400
        if not GOOGLE_PLACES_API_KEY:
            return jsonify({'error': 'Location service not configured'}), 503
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            'place_id': place_id,
            'key': GOOGLE_PLACES_API_KEY,
            'fields': 'formatted_address,geometry,address_component'
        }
        response = requests.get(url, params=params)
        data = response.json()
        if data.get('status') == 'OK':
            result = data['result']
            address_components = result.get('address_components', [])
            location_data = {
                'address': result.get('formatted_address', ''),
                'city': next((comp['long_name'] for comp in address_components
                            if 'locality' in comp['types']), ''),
                'state': next((comp['long_name'] for comp in address_components
                             if 'administrative_area_level_1' in comp['types']), ''),
                'pincode': next((comp['long_name'] for comp in address_components
                               if 'postal_code' in comp['types']), ''),
                'coordinates': {
                    'type': 'Point',
                    'coordinates': [
                        result['geometry']['location']['lng'],
                        result['geometry']['location']['lat']
                    ]
                }
            }
            return jsonify(location_data)
        return jsonify({'error': 'Unable to fetch location details'}), 400
    except Exception as e:
        logger.error(f"Location details error: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/locations/current', methods=['POST'])
def get_current_location():
    try:
        data = request.get_json()
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        location = geolocator.reverse((latitude, longitude))
        if location and location.raw.get('address'):
            address = location.raw['address']
            location_data = {
                'address': f"{address.get('road', '')} {address.get('house_number', '')}".strip(),
                'city': address.get('city', address.get('town', '')),
                'state': address.get('state', ''),
                'pincode': address.get('postcode', ''),
                'coordinates': {
                    'type': 'Point',
                    'coordinates': [longitude, latitude]
                }
            }
            return jsonify(location_data)
        return jsonify({'error': 'Location not found'}), 404
    except Exception as e:
        logger.error(f"Current location error: {str(e)}")
        return jsonify({'error': 'Error processing location'}), 500

@app.route('/select-location', methods=['GET', 'POST'])
def select_location():
    try:
        if request.method == 'POST':
            address = request.form.get('address')
            city = request.form.get('city')
            state = request.form.get('state')
            pincode = request.form.get('pincode')
            if not all([address, city, state, pincode]):
                flash('All fields are required', 'danger')
                return render_template('select_location.html',
                                    username=get_username(),
                                    cart_count=get_cart_count())
            try:
                import time
                full_address = f"{address}, {city}, {state}, {pincode}, India"
                time.sleep(1)
                try:
                    location = geolocator.geocode(full_address)
                except GeocoderTimedOut:
                    time.sleep(2)
                    location = geolocator.geocode(full_address)
                if location:
                    if not hasattr(location, 'latitude') or not hasattr(location, 'longitude'):
                        flash('Unable to verify location coordinates.', 'danger')
                        return render_template('select_location.html',
                                            username=get_username(),
                                            cart_count=get_cart_count())
                    location_data = {
                        'address': address,
                        'city': city,
                        'state': state,
                        'pincode': pincode,
                        'coordinates': {
                            'type': 'Point',
                            'coordinates': [location.longitude, location.latitude]
                        },
                        'formatted_address': location.address
                    }
                    session['selected_location'] = location_data
                    try:
                        mongo.db.delivery_locations.insert_one({
                            'user_id': session.get('user_id'),
                            'location_data': location_data,
                            'created_at': datetime.now()
                        })
                    except Exception as db_error:
                        logger.warning(f"Failed to save location: {str(db_error)}")
                    flash('Location selected successfully!', 'success')
                    return redirect(request.args.get('next') or url_for('index'))
                else:
                    flash('Unable to verify location. Please check the address.', 'danger')
            except Exception as e:
                logger.error(f"Geocoding error: {str(e)}")
                flash('Error processing location.', 'danger')

        recent_locations = []
        if 'user_id' in session:
            recent_locations = list(
                mongo.db.delivery_locations.find(
                    {'user_id': session['user_id']}
                ).sort('created_at', -1).limit(3)
            )
        return render_template('select_location.html',
                             username=get_username(),
                             cart_count=get_cart_count(),
                             recent_locations=recent_locations)
    except Exception as e:
        logger.error(f"Location selection error: {str(e)}")
        flash('An error occurred. Please try again.', 'danger')
        return render_template('select_location.html',
                             username=get_username(),
                             cart_count=get_cart_count())


# ============================================================
# ADMIN ROUTES
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('Welcome, Admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('admin_login.html', username=get_username())

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        mongo.db.products.update_many(
            {'stock': {'$exists': False}},
            {'$set': {'stock': 0}}
        )
    except Exception as e:
        logger.error(f"Error updating products without stock: {str(e)}")

    products = list(mongo.db.products.find())
    orders = list(mongo.db.orders.find().sort('date', -1))
    subscriber_count = mongo.db.newsletter_subscribers.count_documents({'status': 'active'})

    for order in orders:
        if order.get('status') == 'Pending':
            order['status_color'] = 'warning'
        elif order.get('status') == 'Completed':
            order['status_color'] = 'success'
        elif order.get('status') == 'Cancelled':
            order['status_color'] = 'danger'
        else:
            order['status_color'] = 'primary'

    return render_template('admin_dashboard.html',
                         products=products,
                         orders=orders,
                         subscriber_count=subscriber_count,
                         username=get_username())

@app.route('/admin/product/<product_id>')
@admin_required
def admin_get_product(product_id):
    product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
    if product:
        product['_id'] = str(product['_id'])
        return jsonify(product)
    return jsonify({'error': 'Product not found'}), 404

@app.route('/admin/product/add', methods=['POST'])
@admin_required
def admin_add_product():
    try:
        if 'image' not in request.files:
            flash('No image file', 'danger')
            return redirect(url_for('admin_dashboard'))

        file = request.files['image']
        if file.filename == '':
            filename = 'placeholder.jpg'
        else:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(file_path)

        product = {
            'name': request.form.get('name'),
            'category': request.form.get('category'),
            'price': float(request.form.get('price')),
            'description': request.form.get('description'),
            'image': filename,
            'stock': int(request.form.get('stock', 0))
        }

        result = mongo.db.products.insert_one(product)
        if result.inserted_id:
            flash('Product added successfully', 'success')
        else:
            flash('Error adding product', 'danger')
    except Exception as e:
        logger.error(f"Error adding product: {str(e)}")
        flash('Error adding product', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/product/edit', methods=['POST'])
@admin_required
def admin_edit_product():
    try:
        product_id = request.form.get('product_id')
        update_data = {
            'name': request.form.get('name'),
            'category': request.form.get('category'),
            'price': float(request.form.get('price')),
            'description': request.form.get('description'),
            'stock': int(request.form.get('stock', 0))
        }
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(file_path)
                update_data['image'] = filename
                old_product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
                if old_product and 'image' in old_product:
                    old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_product['image'])
                    if os.path.exists(old_image_path) and old_product['image'] != 'placeholder.jpg':
                        os.remove(old_image_path)
        result = mongo.db.products.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            flash('Product updated successfully', 'success')
        else:
            flash('No changes were made', 'info')
    except Exception as e:
        logger.error(f"Error updating product: {str(e)}")
        flash('Error updating product', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/product/<product_id>/delete', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    try:
        product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
        if product and 'image' in product:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image'])
            if os.path.exists(image_path) and product['image'] != 'placeholder.jpg':
                os.remove(image_path)
        mongo.db.products.delete_one({'_id': ObjectId(product_id)})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/order/<order_id>')
@admin_required
def admin_view_order(order_id):
    try:
        order = mongo.db.orders.find_one({'_id': ObjectId(order_id)})
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('admin_dashboard'))
        customer = None
        if order.get('user_id'):
            customer = mongo.db.users.find_one({'_id': ObjectId(order['user_id'])})
        status_map = {'Pending': 'warning', 'Completed': 'success', 'Cancelled': 'danger'}
        order['status_color'] = status_map.get(order.get('status'), 'primary')
        processed_items = []
        for item in order.get('items', []):
            if isinstance(item, dict) and 'product' in item:
                product = item['product']
                if not isinstance(product, dict):
                    product = mongo.db.products.find_one({'_id': ObjectId(product)})
                    if not product:
                        product = {'name': 'Product Not Found', 'price': 0, 'image': 'placeholder.jpg'}
                item['product'] = product
                processed_items.append(item)
        order['items'] = processed_items
        return render_template('admin_view_order.html',
                             order=order, customer=customer, username=get_username())
    except Exception as e:
        logger.error(f"Error viewing order: {str(e)}")
        flash('Error viewing order details', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/<order_id>/update-status', methods=['POST'])
@admin_required
def update_order_status(order_id):
    try:
        new_status = request.form.get('status')
        order = mongo.db.orders.find_one_and_update(
            {'_id': ObjectId(order_id)},
            {'$set': {'status': new_status, 'updated_at': datetime.now()}},
            return_document=True
        )
        if order and order.get('user_id'):
            # Emit real-time status update to the specific user via WebSockets
            room_id = str(order['user_id'])
            socketio.emit('order_status_updated', {
                'order_id': order_id,
                'status': new_status
            }, to=room_id)
            
            mongo.db.notifications.insert_one({
                'user_id': order['user_id'],
                'type': 'order_status',
                'title': 'Order Status Update',
                'message': f'Your order #{order_id} status has been updated to {new_status}',
                'read': False,
                'created_at': datetime.now()
            })
        flash('Order status updated successfully', 'success')
        return redirect(url_for('admin_view_order', order_id=order_id))
    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}")
        flash('Error updating order status', 'danger')
        return redirect(url_for('admin_dashboard'))


# ============================================================
# PUBLIC ROUTES
# ============================================================
@app.route('/')
def index():
    products = list(mongo.db.products.find())
    return render_template('index.html',
                         products=products,
                         cart_count=get_cart_count(),
                         username=get_username(),
                         location=session.get('selected_location'))

@app.route('/shop')
def shop():
    search_query = request.args.get('search', '')
    if search_query:
        products = list(mongo.db.products.find({
            '$or': [
                {'name': {'$regex': search_query, '$options': 'i'}},
                {'description': {'$regex': search_query, '$options': 'i'}}
            ]
        }))
    else:
        products = list(mongo.db.products.find())
    return render_template('shop.html', products=products, cart_count=get_cart_count(), username=get_username())

@app.route('/product/<product_id>')
def product_details(product_id):
    product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
    if not product:
        flash('Product not found', 'danger')
        return redirect(url_for('shop'))
    return render_template('product_details.html', product=product, cart_count=get_cart_count(), username=get_username())


# ============================================================
# AUTH ROUTES
# ============================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = mongo.db.users.find_one({'email': request.form.get('email')})
        if user and user.get('password') and bcrypt.checkpw(request.form.get('password').encode('utf-8'), user['password']):
            session['user_id'] = str(user['_id'])
            flash('Successfully logged in!', 'success')
            return redirect(url_for('index'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html', cart_count=get_cart_count(), username=get_username())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            if not all([username, email, password, confirm_password]):
                flash('All fields are required', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())

            if password != confirm_password:
                flash('Passwords do not match', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())

            existing_user = mongo.db.users.find_one({
                '$or': [{'email': email}, {'username': username}]
            })
            if existing_user:
                flash('Email or username already exists', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            user = {
                'username': username,
                'email': email,
                'password': hashed_password,
                'full_name': username,
                'phone': '',
                'address': '',
                'city': '',
                'state': '',
                'zip_code': '',
                'date_joined': datetime.now(),
                'last_login': datetime.now(),
                'profile_image': None,
                'notifications': {
                    'order_updates': True,
                    'promotions': False,
                    'newsletter': False
                },
                'profile_visibility': 'private'
            }

            result = mongo.db.users.insert_one(user)
            if result.inserted_id:
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Error creating account.', 'danger')
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash('An error occurred during registration.', 'danger')
    return render_template('register.html', cart_count=get_cart_count(), username=get_username())

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out!', 'success')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = mongo.db.users.find_one({'email': email})
        if user:
            token = secrets.token_urlsafe(32)
            expiry = datetime.utcnow() + timedelta(hours=1)
            mongo.db.password_resets.insert_one({
                'user_id': user['_id'],
                'token': token,
                'expiry': expiry
            })
            reset_url = url_for('reset_password', token=token, _external=True)
            try:
                msg = Message('Password Reset Request', recipients=[email],
                    html=render_template('email/reset_password.html',
                        reset_url=reset_url, username=user.get('username', '')))
                mail.send(msg)
                flash('Password reset instructions sent to your email.', 'success')
            except Exception as e:
                logger.error(f"Error sending reset email: {str(e)}")
                flash('Error sending reset email.', 'danger')
        flash('If an account exists with this email, you will receive reset instructions.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html', username=get_username(), cart_count=get_cart_count())

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset_request = mongo.db.password_resets.find_one({
        'token': token,
        'expiry': {'$gt': datetime.utcnow()}
    })
    if not reset_request:
        flash('Invalid or expired reset link', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('reset_password.html')
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.update_one(
            {'_id': reset_request['user_id']},
            {'$set': {'password': hashed_password}}
        )
        mongo.db.password_resets.delete_one({'_id': reset_request['_id']})
        flash('Password updated successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', username=get_username(), cart_count=get_cart_count())

# --- Google OAuth ---
@app.route('/login/google')
def google_login():
    try:
        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
        authorization_endpoint = google_provider_cfg["authorization_endpoint"]
        request_uri = client.prepare_request_uri(
            authorization_endpoint,
            redirect_uri=request.host_url + "login/google/callback",
            scope=["openid", "email", "profile"],
        )
        return redirect(request_uri)
    except Exception as e:
        logger.error(f"Google Login Error: {e}")
        flash("Google login setup error.", "danger")
        return redirect(url_for('login'))

@app.route('/login/google/callback')
def google_callback():
    try:
        code = request.args.get("code")
        if not code:
            flash("Authorization code missing.", "danger")
            return redirect(url_for("login"))

        google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
        token_endpoint = google_provider_cfg["token_endpoint"]
        token_url, headers, body = client.prepare_token_request(
            token_endpoint,
            authorization_response=request.url,
            redirect_url=request.host_url + "login/google/callback",
            code=code
        )
        token_response = requests.post(
            token_url, headers=headers, data=body,
            auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
        )
        if token_response.status_code != 200:
            flash("Failed to authenticate with Google.", "danger")
            return redirect(url_for("login"))

        client.parse_request_body_response(token_response.text)
        userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
        uri, headers, body = client.add_token(userinfo_endpoint)
        userinfo_response = requests.get(uri, headers=headers, data=body)

        if userinfo_response.status_code != 200:
            flash("Failed to retrieve user info from Google.", "danger")
            return redirect(url_for("login"))

        user_info = userinfo_response.json()
        if not user_info.get("email_verified"):
            flash("Google email not verified.", "danger")
            return redirect(url_for("login"))

        email = user_info.get("email")
        name = user_info.get("name", "")
        google_id = user_info.get("sub")
        picture = user_info.get("picture", "")

        if not email:
            flash("Email not received from Google.", "danger")
            return redirect(url_for("login"))

        # FIXED: use mongo.db.users instead of mongo["users"]
        existing_user = mongo.db.users.find_one({"email": email})

        if not existing_user:
            user = {
                "username": email.split("@")[0],
                "email": email,
                "password": None,
                "full_name": name,
                "google_id": google_id,
                "profile_image": picture,
                "date_joined": datetime.utcnow(),
                "last_login": datetime.utcnow(),
                "notifications": {
                    "order_updates": True,
                    "promotions": False,
                    "newsletter": False
                },
                "profile_visibility": "private"
            }
            inserted = mongo.db.users.insert_one(user)
            user_id = inserted.inserted_id
        else:
            mongo.db.users.update_one(
                {"_id": existing_user["_id"]},
                {"$set": {
                    "google_id": google_id,
                    "profile_image": picture,
                    "last_login": datetime.utcnow()
                }}
            )
            user_id = existing_user["_id"]

        session["user_id"] = str(user_id)
        flash("Successfully logged in with Google!", "success")
        return redirect(url_for("index"))
    except Exception as e:
        logger.error(f"Google callback error: {e}")
        flash("Something went wrong during Google login.", "danger")
        return redirect(url_for("login"))


# ============================================================
# CART ROUTES
# ============================================================
@app.route('/cart')
def cart():
    cart_items = []
    total = 0
    if 'user_id' in session:
        user_cart = mongo.db.cart.find_one({'user_id': session['user_id']})
        if user_cart and 'items' in user_cart:
            for item in user_cart['items']:
                product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
                if product:
                    item_total = float(product['price']) * item['quantity']
                    cart_items.append({'product': product, 'quantity': item['quantity'], 'total': item_total})
                    total += item_total
    elif 'guest_cart' in session:
        for item in session['guest_cart']:
            product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_total = float(product['price']) * item['quantity']
                cart_items.append({'product': product, 'quantity': item['quantity'], 'total': item_total})
                total += item_total
    return render_template('cart.html', cart_items=cart_items, total=total, cart_count=get_cart_count(), username=get_username())

@app.route('/cart/add/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Please login to add items to cart'})
    try:
        data = request.get_json()
        quantity = int(data.get('quantity', 1))
        if quantity < 1:
            return jsonify({'success': False, 'error': 'Invalid quantity'})
        product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'})
        current_stock = product.get('stock', 100)
        user_cart = mongo.db.cart.find_one({'user_id': session['user_id']})
        if not user_cart:
            user_cart = {'user_id': session['user_id'], 'items': []}
            mongo.db.cart.insert_one(user_cart)
        existing_item = next((item for item in user_cart['items'] if str(item['product_id']) == product_id), None)
        if existing_item:
            new_quantity = existing_item['quantity'] + quantity
            if new_quantity > current_stock:
                return jsonify({'success': False, 'error': f'Only {current_stock} items in stock.'})
            mongo.db.cart.update_one(
                {'user_id': session['user_id'], 'items.product_id': ObjectId(product_id)},
                {'$inc': {'items.$.quantity': quantity}}
            )
        else:
            if quantity > current_stock:
                return jsonify({'success': False, 'error': f'Only {current_stock} items in stock.'})
            mongo.db.cart.update_one(
                {'user_id': session['user_id']},
                {'$push': {'items': {'product_id': ObjectId(product_id), 'quantity': quantity}}}
            )
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error adding to cart: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cart/remove/<product_id>', methods=['POST'])
def remove_from_cart(product_id):
    try:
        if 'user_id' in session:
            mongo.db.cart.update_one(
                {'user_id': session['user_id']},
                {'$pull': {'items': {'product_id': ObjectId(product_id)}}}
            )
        elif 'guest_cart' in session:
            session['guest_cart'] = [item for item in session['guest_cart'] if item['product_id'] != product_id]
            session.modified = True
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/cart/count')
def get_cart_count_api():
    try:
        return jsonify({'count': get_cart_count()})
    except Exception as e:
        return jsonify({'count': 0})


# ============================================================
# CHECKOUT & ORDER ROUTES
# ============================================================
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = []
    total = 0
    if 'user_id' in session:
        user_cart = mongo.db.cart.find_one({'user_id': session['user_id']})
        if not user_cart or 'items' not in user_cart or not user_cart['items']:
            flash('Your cart is empty', 'warning')
            return redirect(url_for('cart'))
        for item in user_cart['items']:
            product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_total = float(product['price']) * item['quantity']
                cart_items.append({'product': product, 'quantity': item['quantity'], 'total': item_total})
                total += item_total
    elif 'guest_cart' in session:
        if not session['guest_cart']:
            flash('Your cart is empty', 'warning')
            return redirect(url_for('cart'))
        for item in session['guest_cart']:
            product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_total = float(product['price']) * item['quantity']
                cart_items.append({'product': product, 'quantity': item['quantity'], 'total': item_total})
                total += item_total
    else:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('cart'))

    if request.method == 'POST':
        if total <= 0:
            flash('Cart total must be greater than zero to checkout.', 'danger')
            return redirect(url_for('cart'))

        try:
            payment_method = request.form.get('payment_method')
            # SECURITY FIX: Don't store card numbers in DB
            order = {
                'items': cart_items,
                'total': total,
                'status': 'Pending',
                'date': datetime.now(),
                'shipping_address': {
                    'full_name': request.form.get('full_name'),
                    'email': request.form.get('email'),
                    'address': request.form.get('address'),
                    'city': request.form.get('city'),
                    'state': request.form.get('state'),
                    'zip_code': request.form.get('zip_code'),
                    'phone': request.form.get('phone')
                },
                'payment_method': payment_method,
                'payment_status': 'pending'
            }
            if 'user_id' in session:
                order['user_id'] = session['user_id']
                mongo.db.users.update_one(
                    {'_id': ObjectId(session['user_id'])},
                    {'$set': {
                        'full_name': request.form.get('full_name'),
                        'address': request.form.get('address'),
                        'city': request.form.get('city'),
                        'state': request.form.get('state'),
                        'zip_code': request.form.get('zip_code'),
                        'phone': request.form.get('phone')
                    }}
                )
            
            if payment_method != 'cash':
                # Map to Stripe
                order['payment_status'] = 'pending_stripe'
                result = mongo.db.orders.insert_one(order)
                
                line_items = []
                for item in cart_items:
                    line_items.append({
                        'price_data': {
                            'currency': 'inr',
                            'product_data': {
                                'name': item['product']['name'],
                            },
                            'unit_amount': int(float(item['product']['price']) * 100),
                        },
                        'quantity': item['quantity'],
                    })

                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=line_items,
                    mode='payment',
                    success_url=url_for('checkout_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
                    cancel_url=url_for('checkout', _external=True),
                    client_reference_id=str(result.inserted_id)
                )
                return redirect(checkout_session.url)
            else:
                order['payment_status'] = 'cash_on_delivery'
                mongo.db.orders.insert_one(order)
                if 'user_id' in session:
                    mongo.db.cart.delete_one({'user_id': session['user_id']})
                else:
                    session.pop('guest_cart', None)
                
                send_order_email(order, request.form.get('email'))
                flash('Order placed successfully!', 'success')
                return redirect(url_for('order_confirmation'))
        except Exception as e:
            logger.error(f"Checkout error: {str(e)}")
            flash('Error processing your order.', 'danger')
            return redirect(url_for('checkout'))

    user = None
    if 'user_id' in session:
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('checkout.html',
                         cart_items=cart_items, total=total, user=user,
                         cart_count=get_cart_count(), username=get_username())

@app.route('/checkout/success')
def checkout_success():
    session_id = request.args.get('session_id')
    if not session_id:
        flash('Invalid checkout session.', 'danger')
        return redirect(url_for('cart'))
        
    try:
        # Retrieve the session from Stripe
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        order_id = checkout_session.client_reference_id
        
        # Verify the order exists and is pending
        order = mongo.db.orders.find_one({'_id': ObjectId(order_id)})
        if not order or order.get('payment_status') != 'pending_stripe':
            flash('Order not found or already processed.', 'warning')
            return redirect(url_for('order_confirmation'))
            
        # Update order to success
        mongo.db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'payment_status': 'paid_stripe'}}
        )
        
        # Clear Cart
        if 'user_id' in session:
            mongo.db.cart.delete_one({'user_id': session['user_id']})
        else:
            session.pop('guest_cart', None)
            
        # Send Email
        recipient_email = order['shipping_address']['email']
        send_order_email(order, recipient_email)
            
        flash('Payment successful! Order placed successfully!', 'success')
        return redirect(url_for('order_confirmation'))
        
    except Exception as e:
        logger.error(f"Stripe success processing error: {str(e)}")
        flash(f'Payment was successful but we encountered an error: {str(e)}. Please contact support.', 'warning')
        return redirect(url_for('order_confirmation'))

def send_order_email(order, recipient_email):
    try:
        msg = Message('Your Waggy Pet Shop Order Confirmation', 
                      recipients=[recipient_email])
        msg.html = render_template('email/order_confirmation.html', order=order)
        mail.send(msg)
    except Exception as e:
        logger.error(f"Failed to send email receipt: {e}")

@app.route('/order-confirmation')
def order_confirmation():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    order = mongo.db.orders.find_one(
        {'user_id': session['user_id']},
        sort=[('date', -1)]
    )
    if not order:
        flash('Order not found', 'warning')
        return redirect(url_for('shop'))
    return render_template('order_confirmation.html',
                         order=order, cart_count=get_cart_count(), username=get_username())

@app.route('/order/<order_id>')
def view_order(order_id):
    try:
        order = mongo.db.orders.find_one({'_id': ObjectId(order_id)})
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('profile_details'))

        status_map = {'Pending': 'warning', 'Completed': 'success', 'Cancelled': 'danger'}
        order['status_color'] = status_map.get(order.get('status'), 'primary')

        processed_items = []
        total = 0
        for item in order.get('items', []):
            if isinstance(item, dict) and 'product' in item:
                product_data = item['product']
                quantity = item.get('quantity', 1)
                price = float(product_data.get('price', 0))
                item_total = price * quantity
                total += item_total
                processed_items.append({
                    'product': {
                        'name': product_data.get('name', 'Product Not Found'),
                        'price': price,
                        'image': product_data.get('image', 'placeholder.jpg'),
                        'category': product_data.get('category', 'Uncategorized')
                    },
                    'quantity': quantity,
                    'total': item_total
                })
        order['items'] = processed_items
        order['total'] = total

        if 'date' in order and isinstance(order['date'], str):
            try:
                order['date'] = datetime.strptime(order['date'], '%Y-%m-%d %H:%M:%S')
            except:
                order['date'] = datetime.now()
        elif 'date' not in order:
            order['date'] = datetime.now()

        if 'shipping_address' not in order or not isinstance(order['shipping_address'], dict):
            order['shipping_address'] = {
                'full_name': 'N/A', 'address': 'N/A', 'city': 'N/A',
                'state': 'N/A', 'zip_code': '000000', 'phone': '0000000000'
            }
        if 'payment_details' not in order or not isinstance(order['payment_details'], dict):
            order['payment_details'] = {}

        return render_template('order_details.html', order=order, cart_count=get_cart_count(), username=get_username())
    except Exception as e:
        logger.error(f"Error viewing order: {str(e)}")
        flash('Error viewing order details', 'danger')
        return redirect(url_for('profile_details'))

@app.route('/order/<order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    try:
        order = mongo.db.orders.find_one({'_id': ObjectId(order_id)})
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('profile_details'))

        # Admins can cancel any order, but users can only cancel their own
        is_admin = session.get('is_admin', False)
        if not is_admin and str(order.get('user_id')) != str(session.get('user_id')):
            flash('Unauthorized', 'danger')
            return redirect(url_for('profile_details'))

        if order.get('status') != 'Pending':
            flash('Only Pending orders can be cancelled.', 'danger')
            return redirect(url_for('profile_details'))

        mongo.db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'status': 'Cancelled'}}
        )
        flash('Order cancelled successfully.', 'success')
    except Exception as e:
        logger.error(f"Error cancelling order: {str(e)}")
        flash('Error cancelling order.', 'danger')
    
    # If the request came from admin dashboard, redirect there
    referer = request.headers.get("Referer")
    if referer and 'admin' in referer:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('profile_details'))


# ============================================================
# PROFILE ROUTES
# ============================================================
@app.route('/profile')
@login_required
def profile():
    return redirect(url_for('profile_details'))

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        username = request.form.get('username')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        if not all([username, email, full_name]):
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('profile_details'))
        existing_user = mongo.db.users.find_one({
            '_id': {'$ne': ObjectId(session['user_id'])},
            '$or': [{'username': username}, {'email': email}]
        })
        if existing_user:
            flash('Username or email is already taken', 'danger')
            return redirect(url_for('profile_details'))
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'username': username, 'email': email, 'full_name': full_name, 'phone': phone}}
        )
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}")
        flash('An error occurred', 'danger')
    return redirect(url_for('profile_details'))

@app.route('/profile/details')
@login_required
def profile_details():
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    addresses = list(mongo.db.addresses.find({'user_id': session['user_id']}))
    recent_orders = list(mongo.db.orders.find({'user_id': session['user_id']}).sort('date', -1).limit(5))
    status_map = {'Pending': 'warning', 'Completed': 'success', 'Cancelled': 'danger'}
    for order in recent_orders:
        order['status_color'] = status_map.get(order.get('status'), 'primary')
    return render_template('profile_details.html', user=user, recent_orders=recent_orders, addresses=addresses, cart_count=get_cart_count(), username=get_username())

@app.route('/profile/image/update', methods=['POST'])
@login_required
def update_profile_image():
    try:
        if 'profile_image' not in request.files:
            flash('No image file provided', 'danger')
            return redirect(url_for('profile_details'))
        file = request.files['profile_image']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('profile_details'))
        if file:
            profiles_dir = os.path.join(app.static_folder, 'images', 'profiles')
            os.makedirs(profiles_dir, exist_ok=True)
            img = Image.open(file)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            filename = secure_filename(file.filename)
            unique_filename = f"{session['user_id']}_{int(datetime.now().timestamp())}_{filename}"
            file_path = os.path.join(profiles_dir, unique_filename)
            img.save(file_path, quality=85, optimize=True)
            mongo.db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': {'profile_image': unique_filename}}
            )
            flash('Profile image updated successfully!', 'success')
            return redirect(url_for('profile_details'))
    except Exception as e:
        logger.error(f"Error updating profile image: {str(e)}")
        flash('Error updating profile image', 'danger')
        return redirect(url_for('profile_details'))

@app.route('/profile/image/remove', methods=['POST'])
@login_required
def remove_profile_image():
    try:
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$unset': {'profile_image': ''}}
        )
        flash('Profile custom image removed successfully', 'success')
    except Exception as e:
        logger.error(f"Error removing profile image: {str(e)}")
        flash('Error removing profile image', 'danger')
    return redirect(url_for('profile_details'))

@app.route('/profile/password/update', methods=['POST'])
@login_required
def update_password():
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('settings'))
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('settings'))
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not user or not bcrypt.checkpw(current_password.encode('utf-8'), user['password']):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('settings'))
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'password': hashed_password}}
        )
        flash('Password updated successfully', 'success')
    except Exception as e:
        logger.error(f"Error updating password: {str(e)}")
        flash('An error occurred', 'danger')
    return redirect(url_for('settings'))

@app.route('/profile/notifications/update', methods=['POST'])
@login_required
def update_notifications():
    try:
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'notifications': {
                'order_updates': request.form.get('order_updates') == 'on',
                'promotions': request.form.get('promotions') == 'on',
                'newsletter': request.form.get('newsletter') == 'on'
            }}}
        )
        flash('Notification settings updated', 'success')
    except Exception as e:
        logger.error(f"Error updating notifications: {str(e)}")
        flash('Error updating notification settings', 'danger')
    return redirect(url_for('settings'))

@app.route('/profile/privacy/update', methods=['POST'])
@login_required
def update_privacy():
    try:
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'profile_visibility': request.form.get('profile_visibility', 'private')}}
        )
        flash('Privacy settings updated', 'success')
    except Exception as e:
        logger.error(f"Error updating privacy: {str(e)}")
        flash('Error updating privacy settings', 'danger')
    return redirect(url_for('settings'))

@app.route('/profile/delete', methods=['POST'])
@login_required
def delete_account():
    try:
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not user or not user.get('password') or not bcrypt.checkpw(request.form.get('password').encode('utf-8'), user['password']):
            flash('Incorrect password', 'danger')
            return redirect(url_for('settings'))
        mongo.db.users.delete_one({'_id': ObjectId(session['user_id'])})
        mongo.db.addresses.delete_many({'user_id': session['user_id']})
        mongo.db.cart.delete_one({'user_id': session['user_id']})
        mongo.db.orders.update_many(
            {'user_id': session['user_id']},
            {'$set': {'user_id': None, 'status': 'Deleted'}}
        )
        session.clear()
        flash('Your account has been deleted', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error deleting account: {str(e)}")
        flash('Error deleting account', 'danger')
        return redirect(url_for('settings'))


# ============================================================
# SETTINGS & HELP ROUTES
# ============================================================
@app.route('/help')
@login_required
def help():
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('help.html', user=user, cart_count=get_cart_count(), username=get_username())

@app.route('/settings')
@login_required
def settings():
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('settings.html', user=user, cart_count=get_cart_count(), username=get_username())

@app.route('/contact/support', methods=['POST'])
@login_required
def contact_support():
    try:
        mongo.db.support_messages.insert_one({
            'user_id': session['user_id'],
            'subject': request.form.get('subject'),
            'message': request.form.get('message'),
            'date': datetime.now(),
            'status': 'Pending'
        })
        flash('Your message has been sent.', 'success')
    except Exception as e:
        logger.error(f"Error sending support message: {str(e)}")
        flash('Error sending message.', 'danger')
    return redirect(url_for('help'))


# ============================================================
# ADDRESS MANAGEMENT
# ============================================================
@app.route('/address/add', methods=['POST'])
@login_required
def add_address():
    try:
        address = {
            'user_id': session['user_id'],
            'name': request.form.get('name'),
            'address': request.form.get('address'),
            'city': request.form.get('city'),
            'state': request.form.get('state'),
            'zip_code': request.form.get('zip_code'),
            'country': request.form.get('country'),
            'is_default': False
        }
        existing = list(mongo.db.addresses.find({'user_id': session['user_id']}))
        if not existing:
            address['is_default'] = True
        mongo.db.addresses.insert_one(address)
        flash('Address added successfully', 'success')
    except Exception as e:
        logger.error(f"Error adding address: {str(e)}")
        flash('Error adding address', 'danger')
    return redirect(url_for('profile'))

@app.route('/address/<address_id>')
@login_required
def get_address(address_id):
    try:
        address = mongo.db.addresses.find_one({
            '_id': ObjectId(address_id), 'user_id': session['user_id']
        })
        if address:
            address['_id'] = str(address['_id'])
            return jsonify(address)
        return jsonify({'error': 'Address not found'}), 404
    except Exception as e:
        return jsonify({'error': 'Server error'}), 500

@app.route('/address/<address_id>/edit', methods=['POST'])
@login_required
def edit_address(address_id):
    try:
        result = mongo.db.addresses.update_one(
            {'_id': ObjectId(address_id), 'user_id': session['user_id']},
            {'$set': {
                'name': request.form.get('name'),
                'address': request.form.get('address'),
                'city': request.form.get('city'),
                'state': request.form.get('state'),
                'zip_code': request.form.get('zip_code'),
                'country': request.form.get('country')
            }}
        )
        flash('Address updated successfully' if result.modified_count > 0 else 'No changes made', 'success' if result.modified_count > 0 else 'info')
    except Exception as e:
        logger.error(f"Error updating address: {str(e)}")
        flash('Error updating address', 'danger')
    return redirect(url_for('profile'))

@app.route('/address/<address_id>/delete', methods=['POST'])
@login_required
def delete_address(address_id):
    try:
        address = mongo.db.addresses.find_one({
            '_id': ObjectId(address_id), 'user_id': session['user_id']
        })
        if address and address.get('is_default'):
            other = mongo.db.addresses.find_one({
                'user_id': session['user_id'], '_id': {'$ne': ObjectId(address_id)}
            })
            if other:
                mongo.db.addresses.update_one({'_id': other['_id']}, {'$set': {'is_default': True}})
        result = mongo.db.addresses.delete_one({
            '_id': ObjectId(address_id), 'user_id': session['user_id']
        })
        return jsonify({'success': result.deleted_count > 0})
    except Exception as e:
        return jsonify({'error': 'Server error'}), 500

@app.route('/address/<address_id>/set-default', methods=['POST'])
@login_required
def set_default_address(address_id):
    try:
        mongo.db.addresses.update_many(
            {'user_id': session['user_id']}, {'$set': {'is_default': False}}
        )
        result = mongo.db.addresses.update_one(
            {'_id': ObjectId(address_id), 'user_id': session['user_id']},
            {'$set': {'is_default': True}}
        )
        return jsonify({'success': result.modified_count > 0})
    except Exception as e:
        return jsonify({'error': 'Server error'}), 500


# ============================================================
# NEWSLETTER ROUTES
# ============================================================
@app.route('/newsletter/subscribe', methods=['POST'])
def subscribe_newsletter():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({'success': False, 'message': 'Please enter a valid email'})
        if mongo.db.newsletter_subscribers.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Already subscribed'})
        mongo.db.newsletter_subscribers.insert_one({
            'email': email,
            'subscribed_at': datetime.now(),
            'status': 'active',
            'unsubscribe_token': secrets.token_urlsafe(24)
        })
        return jsonify({'success': True, 'message': 'Thank you for subscribing!'})
    except Exception as e:
        logger.error(f"Newsletter error: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'})

@app.route('/newsletter/unsubscribe/<token>')
def unsubscribe_newsletter(token):
    try:
        subscriber = mongo.db.newsletter_subscribers.find_one({'unsubscribe_token': token})
        if not subscriber:
            flash('Invalid unsubscribe link', 'danger')
            return redirect(url_for('index'))
        mongo.db.newsletter_subscribers.update_one(
            {'_id': subscriber['_id']},
            {'$set': {'status': 'unsubscribed', 'unsubscribed_at': datetime.now()}}
        )
        flash('Successfully unsubscribed', 'success')
    except Exception as e:
        logger.error(f"Unsubscribe error: {str(e)}")
        flash('An error occurred', 'danger')
    return redirect(url_for('index'))

@app.route('/admin/newsletter')
@admin_required
def admin_newsletter():
    subscribers = list(mongo.db.newsletter_subscribers.find().sort('subscribed_at', -1))
    return render_template('admin_newsletter.html', subscribers=subscribers, username=get_username())

@app.route('/admin/newsletter/send', methods=['POST'])
@admin_required
def send_newsletter():
    try:
        subject = request.form.get('subject')
        content = request.form.get('content')
        if not subject or not content:
            flash('Subject and content are required', 'danger')
            return redirect(url_for('admin_newsletter'))
        subscribers = list(mongo.db.newsletter_subscribers.find({'status': 'active'}))
        logger.info(f"Newsletter '{subject}' would be sent to {len(subscribers)} subscribers")
        mongo.db.newsletters.insert_one({
            'subject': subject, 'content': content,
            'sent_at': datetime.now(), 'sent_to': len(subscribers), 'status': 'sent'
        })
        flash(f'Newsletter sent to {len(subscribers)} subscribers', 'success')
    except Exception as e:
        logger.error(f"Newsletter send error: {str(e)}")
        flash('Error sending newsletter', 'danger')
    return redirect(url_for('admin_newsletter'))

@app.route('/admin/newsletter/subscribers/export')
@admin_required
def export_subscribers():
    try:
        subscribers = list(mongo.db.newsletter_subscribers.find(
            {'status': 'active'}, {'email': 1, 'subscribed_at': 1, '_id': 0}
        ).sort('subscribed_at', -1))
        output = "Email,Subscribed Date\n"
        for sub in subscribers:
            output += f"{sub['email']},{sub['subscribed_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        return Response(output, mimetype='text/csv',
                       headers={'Content-Disposition': 'attachment;filename=subscribers.csv'})
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        flash('Error exporting subscribers', 'danger')
        return redirect(url_for('admin_newsletter'))


# ============================================================
# AI INTEGRATION (Phase 3)
# ============================================================
@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    try:
        if not groq_client:
            return jsonify({'success': False, 'message': 'AI service is currently unavailable. (Missing API Key)'})
        
        data = request.get_json()
        user_message = data.get('message', '').strip()
        chat_history = data.get('history', [])
        
        if not user_message:
            return jsonify({'success': False, 'message': 'Say something!'})

        # Fetch some products to recommend if relevant
        products = list(mongo.db.products.find({}, {'_id': 1, 'name': 1, 'category': 1, 'price': 1}).limit(20))
        product_context = "Available Products in Store:\n"
        for p in products:
            product_context += f"- {p['name']} (Category: {p['category']}, Price: ₹{p['price']}, ID: {str(p['_id'])})\n"

        system_prompt = f"""
You are "WaggyAI", a highly knowledgeable, friendly, and expert pet care assistant for the Waggy Pet Shop e-commerce platform.
Your goals:
1. Provide excellent, safe, and professional pet care advice based on best practices.
2. Recommend products from our store when they match the user's needs.
3. Keep responses concise, engaging, and structured (use bullet points if helpful).
4. Never provide dangerous medical advice—always recommend consulting a vet for emergencies.

{product_context}

When recommending a product, mention its exact name as listed above so the user knows we carry it.

Current User: {get_username() if get_username() else 'Guest'}
"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Append up to last 5 history messages to maintain context
        for msg in chat_history[-5:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            
        messages.append({"role": "user", "content": user_message})

        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=600,
            top_p=0.9,
            stream=False
        )
        
        ai_response = completion.choices[0].message.content

        # Save conversation to db if user is logged in
        if 'user_id' in session:
            mongo.db.ai_conversations.insert_one({
                'user_id': session['user_id'],
                'user_message': user_message,
                'ai_response': ai_response,
                'timestamp': datetime.now()
            })

        return jsonify({'success': True, 'message': ai_response})
    
    except Exception as e:
        logger.error(f"AI Chat error: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred connecting to the AI brain. Please try again.'})


@app.route('/api/ai/product-insight/<product_id>')
def ai_product_insight(product_id):
    try:
        if not groq_client:
            return jsonify({'success': False, 'message': 'AI unavailable.'})
            
        product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
        if not product:
            return jsonify({'success': False})
            
        prompt = f"Write a very short (2 sentences max) fun, engaging, and convincing reason why a pet owner should buy '{product['name']}' ({product['category']}): {product['description']}. Use an emoji."
        
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=60,
            stream=False
        )
        
        return jsonify({'success': True, 'insight': completion.choices[0].message.content})
    except Exception as e:
        logger.error(f"AI Insight error: {str(e)}")
        return jsonify({'success': False})

# ============================================================
# HEALTH CHECK (for Vercel / monitoring)
# ============================================================
@app.route('/api/health')
def health_check():
    try:
        mongo.db.command('ping')
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except:
        return jsonify({'status': 'unhealthy', 'database': 'disconnected'}), 503


# ============================================================
# WEBSOCKETS (REAL-TIME UPDATES)
# ============================================================
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        # User joins a room named by their user_id
        join_room(str(session['user_id']))
        logger.info(f"User {session['user_id']} connected to WebSocket room")

# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, allow_unsafe_werkzeug=True)