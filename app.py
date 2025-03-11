from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, Response
from flask_pymongo import PyMongo
from bson import ObjectId
import bcrypt
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps
import logging
import re
from PIL import Image
import io

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# MongoDB Configuration
try:
    app.config["MONGO_URI"] = "mongodb://localhost:27017/Petshop"
    mongo = PyMongo(app)
    # Test the connection
    mongo.db.command('ping')
    logger.info("Successfully connected to MongoDB!")
    
    # Migrate existing users to add date_joined field if missing
    users_without_date = mongo.db.users.find({'date_joined': {'$exists': False}})
    for user in users_without_date:
        mongo.db.users.update_one(
            {'_id': user['_id']},
            {'$set': {'date_joined': datetime.now()}}
        )
        logger.info(f"Added date_joined field to user: {user['username']}")
except Exception as e:
    logger.error(f"MongoDB connection error: {str(e)}")
    raise

# Make mongo available to all templates
@app.context_processor
def inject_mongo():
    return dict(mongo=mongo)

app.config['UPLOAD_FOLDER'] = 'static/images'

# Admin credentials (in production, use environment variables)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # In production, use hashed password

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

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

# Admin Routes
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
    # Update any products without stock field
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
    
    # Add status colors for orders
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
            # If no file is selected, use a default image
            filename = 'placeholder.jpg'
        else:
            # Process and save the uploaded image
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Create directory if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Save the file
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
                # Process and save the new image
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Create directory if it doesn't exist
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                # Save the file
                file.save(file_path)
                update_data['image'] = filename
                
                # Delete old image if it exists
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
            flash('No changes were made to the product', 'info')
            
    except Exception as e:
        logger.error(f"Error updating product: {str(e)}")
        flash('Error updating product', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/product/<product_id>/delete', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    try:
        # Optionally delete the image file
        product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
        if product and 'image' in product:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image'])
            if os.path.exists(image_path):
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
        
        # Get customer details
        customer = None
        if order.get('user_id'):
            customer = mongo.db.users.find_one({'_id': ObjectId(order['user_id'])})
        
        # Add status color
        if order.get('status') == 'Pending':
            order['status_color'] = 'warning'
        elif order.get('status') == 'Completed':
            order['status_color'] = 'success'
        elif order.get('status') == 'Cancelled':
            order['status_color'] = 'danger'
        else:
            order['status_color'] = 'primary'
        
        # Process order items
        processed_items = []
        for item in order.get('items', []):
            if isinstance(item, dict) and 'product' in item:
                product = item['product']
                if not isinstance(product, dict):
                    # If product is not a dictionary, try to fetch it from database
                    product = mongo.db.products.find_one({'_id': ObjectId(product)})
                    if not product:
                        product = {
                            'name': 'Product Not Found',
                            'price': 0,
                            'image': 'placeholder.jpg'
                        }
                item['product'] = product
                processed_items.append(item)
        
        order['items'] = processed_items
        
        return render_template('admin_view_order.html', 
                             order=order, 
                             customer=customer,
                             username=get_username())
                             
    except Exception as e:
        logger.error(f"Error viewing order: {str(e)}")
        flash('Error viewing order details', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/<order_id>/update-status', methods=['POST'])
@admin_required
def update_order_status(order_id):
    try:
        new_status = request.form.get('status')
        
        # Update order status
        order = mongo.db.orders.find_one_and_update(
            {'_id': ObjectId(order_id)},
            {'$set': {
                'status': new_status,
                'updated_at': datetime.now()
            }},
            return_document=True
        )
        
        # Send notification to user if they exist
        if order and order.get('user_id'):
            notification = {
                'user_id': order['user_id'],
                'type': 'order_status',
                'title': 'Order Status Update',
                'message': f'Your order #{order_id} status has been updated to {new_status}',
                'read': False,
                'created_at': datetime.now()
            }
            mongo.db.notifications.insert_one(notification)
        
        flash('Order status updated successfully', 'success')
        return redirect(url_for('admin_view_order', order_id=order_id))
        
    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}")
        flash('Error updating order status', 'danger')
        return redirect(url_for('admin_dashboard'))

# Currency conversion constant (1 USD = 75 INR approximately)
USD_TO_INR_RATE = 75

@app.template_filter('usd_to_inr')
def usd_to_inr(amount):
    """Convert USD to INR"""
    return "₹{:.2f}".format(float(amount) * USD_TO_INR_RATE)

# Basic Routes
@app.route('/')
def index():
    products = list(mongo.db.products.find())
    return render_template('index.html', products=products, cart_count=get_cart_count(), username=get_username())

@app.route('/shop')
def shop():
    search_query = request.args.get('search', '')
    if search_query:
        # Search in name and description
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = mongo.db.users.find_one({'email': request.form.get('email')})
        if user and bcrypt.checkpw(request.form.get('password').encode('utf-8'), user['password']):
            session['user_id'] = str(user['_id'])
            flash('Successfully logged in!', 'success')
            return redirect(url_for('index'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html', cart_count=get_cart_count(), username=get_username())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            logger.debug(f"Registration attempt for username: {username}, email: {email}")
            
            # Validate input
            if not all([username, email, password, confirm_password]):
                logger.warning("Missing required fields in registration form")
                flash('All fields are required', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())
                
            if password != confirm_password:
                logger.warning("Password mismatch in registration form")
                flash('Passwords do not match', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())
            
            # Check if user already exists
            existing_user = mongo.db.users.find_one({
                '$or': [
                    {'email': email},
                    {'username': username}
                ]
            })
            
            if existing_user:
                logger.warning(f"Registration attempt with existing email/username: {email}/{username}")
                flash('Email or username already exists', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())
            
            # Hash the password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            # Create user document with all necessary fields
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
            
            # Insert user into database
            try:
                result = mongo.db.users.insert_one(user)
                logger.info(f"Successfully registered user: {username}")
                
                if result.inserted_id:
                    flash('Registration successful! Please login.', 'success')
                    return redirect(url_for('login'))
                else:
                    logger.error("Failed to insert user into database")
                    flash('Error creating account. Please try again.', 'danger')
                    return render_template('register.html', cart_count=get_cart_count(), username=get_username())
                    
            except Exception as db_error:
                logger.error(f"Database error during registration: {str(db_error)}")
                flash('Database error occurred. Please try again.', 'danger')
                return render_template('register.html', cart_count=get_cart_count(), username=get_username())
                
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'danger')
            return render_template('register.html', cart_count=get_cart_count(), username=get_username())
            
    return render_template('register.html', cart_count=get_cart_count(), username=get_username())

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out!', 'success')
    return redirect(url_for('login'))

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
                    cart_items.append({
                        'product': product,
                        'quantity': item['quantity'],
                        'total': item_total
                    })
                    total += item_total
    elif 'guest_cart' in session:
        for item in session['guest_cart']:
            product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_total = float(product['price']) * item['quantity']
                cart_items.append({
                    'product': product,
                    'quantity': item['quantity'],
                    'total': item_total
                })
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
            
        # Check if product exists
        product = mongo.db.products.find_one({'_id': ObjectId(product_id)})
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'})
            
        # Get current stock (default to 100 if not set)
        current_stock = product.get('stock', 100)
        
        # Get or create cart for logged-in user
        user_cart = mongo.db.cart.find_one({'user_id': session['user_id']})
        if not user_cart:
            user_cart = {
                'user_id': session['user_id'],
                'items': []
            }
            mongo.db.cart.insert_one(user_cart)
        
        # Check if product already exists in cart
        existing_item = next((item for item in user_cart['items'] if str(item['product_id']) == product_id), None)
        
        if existing_item:
            # Calculate new total quantity
            new_quantity = existing_item['quantity'] + quantity
            
            # Check if new total would exceed stock
            if new_quantity > current_stock:
                return jsonify({
                    'success': False, 
                    'error': f'Not enough stock available. Only {current_stock} items in stock.'
                })
            
            # Update quantity if product exists
            mongo.db.cart.update_one(
                {
                    'user_id': session['user_id'],
                    'items.product_id': ObjectId(product_id)
                },
                {'$inc': {'items.$.quantity': quantity}}
            )
        else:
            # Check if requested quantity exceeds stock
            if quantity > current_stock:
                return jsonify({
                    'success': False, 
                    'error': f'Not enough stock available. Only {current_stock} items in stock.'
                })
            
            # Add new item to cart
            mongo.db.cart.update_one(
                {'user_id': session['user_id']},
                {
                    '$push': {
                        'items': {
                            'product_id': ObjectId(product_id),
                            'quantity': quantity
                        }
                    }
                }
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
        count = get_cart_count()
        logger.debug(f"Cart count: {count}")
        return jsonify({'count': count})
    except Exception as e:
        logger.error(f"Error getting cart count: {str(e)}")
        return jsonify({'count': 0})

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = []
    total = 0
    
    if 'user_id' in session:
        user_cart = mongo.db.cart.find_one({'user_id': session['user_id']})
        if not user_cart or 'items' not in user_cart or not user_cart['items']:
            flash('Your cart is empty', 'warning')
            return redirect(url_for('cart'))
        
        # Get cart items with product details
        for item in user_cart['items']:
            product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_total = float(product['price']) * item['quantity']
                cart_items.append({
                    'product': product,
                    'quantity': item['quantity'],
                    'total': item_total
                })
                total += item_total
    elif 'guest_cart' in session:
        if not session['guest_cart']:
            flash('Your cart is empty', 'warning')
            return redirect(url_for('cart'))
        
        for item in session['guest_cart']:
            product = mongo.db.products.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_total = float(product['price']) * item['quantity']
                cart_items.append({
                    'product': product,
                    'quantity': item['quantity'],
                    'total': item_total
                })
                total += item_total
    
    if request.method == 'POST':
        try:
            payment_method = request.form.get('payment_method')
            payment_details = {}
            
            # Collect payment details based on method
            if payment_method == 'card':
                payment_details = {
                    'card_number': request.form.get('card_number'),
                    'card_expiry': request.form.get('card_expiry'),
                    'card_name': request.form.get('card_name'),
                    # Don't store CVV for security
                }
            elif payment_method == 'upi':
                payment_details = {
                    'upi_id': request.form.get('upi_id')
                }
            
            # Create order
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
                'payment_details': payment_details
            }
            
            # If user is logged in, save shipping info to profile
            if 'user_id' in session:
                order['user_id'] = session['user_id']
                mongo.db.users.update_one(
                    {'_id': ObjectId(session['user_id'])},
                    {'$set': {
                        'full_name': request.form.get('full_name'),
                        'email': request.form.get('email'),
                        'address': request.form.get('address'),
                        'city': request.form.get('city'),
                        'state': request.form.get('state'),
                        'zip_code': request.form.get('zip_code'),
                        'phone': request.form.get('phone')
                    }}
                )
            
            # Insert order and clear cart
            mongo.db.orders.insert_one(order)
            if 'user_id' in session:
                mongo.db.cart.delete_one({'user_id': session['user_id']})
            else:
                session.pop('guest_cart', None)
            
            flash('Order placed successfully!', 'success')
            return redirect(url_for('order_confirmation'))
            
        except Exception as e:
            flash('Error processing your order. Please try again.', 'danger')
            return redirect(url_for('checkout'))
    
    # Get user details for pre-filling the form if logged in
    user = None
    if 'user_id' in session:
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    return render_template('checkout.html', 
                         cart_items=cart_items, 
                         total=total, 
                         user=user,
                         cart_count=get_cart_count(),
                         username=get_username())

@app.route('/order-confirmation')
def order_confirmation():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    # Get the most recent order for this user
    order = mongo.db.orders.find_one(
        {'user_id': session['user_id']},
        sort=[('date', -1)]  # Sort by date descending to get the most recent
    )
    
    if not order:
        flash('Order not found', 'warning')
        return redirect(url_for('shop'))
    
    return render_template('order_confirmation.html',
                         order=order,
                         cart_count=get_cart_count(),
                         username=get_username())

# Profile Routes
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    addresses = list(mongo.db.addresses.find({'user_id': session['user_id']}))
    
    return render_template('profile.html', user=user, addresses=addresses, cart_count=get_cart_count(), username=get_username())

@app.route('/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # Get form data
        username = request.form.get('username')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        
        # Validate required fields
        if not all([username, email, full_name]):
            flash('Please fill in all required fields', 'danger')
            return redirect(url_for('profile'))
        
        # Check if username or email is already taken by another user
        existing_user = mongo.db.users.find_one({
            '_id': {'$ne': ObjectId(session['user_id'])},
            '$or': [
                {'username': username},
                {'email': email}
            ]
        })
        
        if existing_user:
            flash('Username or email is already taken', 'danger')
            return redirect(url_for('profile'))
        
        # Update user profile
        update_data = {
            'username': username,
            'email': email,
            'full_name': full_name,
            'phone': phone
        }
        
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': update_data}
        )
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
        
    except Exception as e:
        logger.error(f"Error updating profile: {str(e)}")
        flash('An error occurred while updating your profile', 'danger')
        return redirect(url_for('profile'))

@app.route('/profile/details')
def profile_details():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    recent_orders = list(mongo.db.orders.find({'user_id': session['user_id']}).sort('date', -1).limit(5))
    
    # Add status colors for orders
    for order in recent_orders:
        if order.get('status') == 'Pending':
            order['status_color'] = 'warning'
        elif order.get('status') == 'Completed':
            order['status_color'] = 'success'
        elif order.get('status') == 'Cancelled':
            order['status_color'] = 'danger'
        else:
            order['status_color'] = 'primary'
    
    return render_template('profile_details.html', user=user, recent_orders=recent_orders, cart_count=get_cart_count(), username=get_username())

@app.route('/help')
def help():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('help.html', user=user, cart_count=get_cart_count(), username=get_username())

@app.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('settings.html', user=user, cart_count=get_cart_count(), username=get_username())

@app.route('/contact/support', methods=['POST'])
def contact_support():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        support_message = {
            'user_id': session['user_id'],
            'subject': request.form.get('subject'),
            'message': request.form.get('message'),
            'date': datetime.now(),
            'status': 'Pending'
        }
        
        mongo.db.support_messages.insert_one(support_message)
        flash('Your message has been sent. We will get back to you soon.', 'success')
    except Exception as e:
        logger.error(f"Error sending support message: {str(e)}")
        flash('Error sending message. Please try again.', 'danger')
    
    return redirect(url_for('help'))

@app.route('/profile/notifications/update', methods=['POST'])
def update_notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        update_data = {
            'notifications': {
                'order_updates': request.form.get('order_updates') == 'on',
                'promotions': request.form.get('promotions') == 'on',
                'newsletter': request.form.get('newsletter') == 'on'
            }
        }
        
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': update_data}
        )
        
        flash('Notification settings updated successfully', 'success')
    except Exception as e:
        logger.error(f"Error updating notification settings: {str(e)}")
        flash('Error updating notification settings', 'danger')
    
    return redirect(url_for('settings'))

@app.route('/profile/privacy/update', methods=['POST'])
def update_privacy():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        update_data = {
            'profile_visibility': request.form.get('profile_visibility', 'private')
        }
        
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': update_data}
        )
        
        flash('Privacy settings updated successfully', 'success')
    except Exception as e:
        logger.error(f"Error updating privacy settings: {str(e)}")
        flash('Error updating privacy settings', 'danger')
    
    return redirect(url_for('settings'))

@app.route('/profile/delete', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not user or not bcrypt.checkpw(request.form.get('password').encode('utf-8'), user['password']):
            flash('Incorrect password', 'danger')
            return redirect(url_for('settings'))
        
        # Delete user's data
        mongo.db.users.delete_one({'_id': ObjectId(session['user_id'])})
        mongo.db.addresses.delete_many({'user_id': session['user_id']})
        mongo.db.cart.delete_one({'user_id': session['user_id']})
        mongo.db.orders.update_many(
            {'user_id': session['user_id']},
            {'$set': {'user_id': None, 'status': 'Deleted'}}
        )
        
        # Clear session
        session.clear()
        flash('Your account has been deleted', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error deleting account: {str(e)}")
        flash('Error deleting account', 'danger')
        return redirect(url_for('settings'))

@app.route('/order/<order_id>')
def view_order(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # Find the order by ObjectId
        order = mongo.db.orders.find_one({'_id': ObjectId(order_id)})
        
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('profile_details'))
        
        # Add status color
        if order.get('status') == 'Pending':
            order['status_color'] = 'warning'
        elif order.get('status') == 'Completed':
            order['status_color'] = 'success'
        elif order.get('status') == 'Cancelled':
            order['status_color'] = 'danger'
        else:
            order['status_color'] = 'primary'
        
        # Process order items to ensure all required data is available
        processed_items = []
        total = 0
        
        for item in order.get('items', []):
            if isinstance(item, dict) and 'product' in item:
                product_data = item['product']
                quantity = item.get('quantity', 1)
                
                # Calculate item total
                price = float(product_data.get('price', 0))
                item_total = price * quantity
                total += item_total
                
                processed_item = {
                    'product': {
                        'name': product_data.get('name', 'Product Not Found'),
                        'price': price,
                        'image': product_data.get('image', 'placeholder.jpg'),
                        'category': product_data.get('category', 'Uncategorized')
                    },
                    'quantity': quantity,
                    'total': item_total
                }
                processed_items.append(processed_item)
        
        order['items'] = processed_items
        order['total'] = total
        
        return render_template('order_details.html', 
                             order=order,
                             cart_count=get_cart_count(),
                             username=get_username())
                             
    except Exception as e:
        logger.error(f"Error viewing order: {str(e)}")
        flash('Error viewing order details', 'danger')
        return redirect(url_for('profile_details'))

# Profile Image Upload Route
@app.route('/profile/image/update', methods=['POST'])
def update_profile_image():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login to update your profile image'})
    
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image file provided'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No selected file'})
        
        if file:
            # Create profiles directory if it doesn't exist
            profiles_dir = os.path.join(app.static_folder, 'images', 'profiles')
            os.makedirs(profiles_dir, exist_ok=True)
            
            # Read and resize the image
            img = Image.open(file)
            
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            
            # Resize image to 200x200 pixels while maintaining aspect ratio
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_filename = f"{session['user_id']}_{int(datetime.now().timestamp())}_{filename}"
            
            # Save the resized image
            file_path = os.path.join(profiles_dir, unique_filename)
            img.save(file_path, quality=85, optimize=True)
            
            # Update user's profile image in database
            mongo.db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$set': {'profile_image': unique_filename}}
            )
            
            return jsonify({
                'success': True,
                'message': 'Profile image updated successfully',
                'image_url': url_for('static', filename=f'images/profiles/{unique_filename}')
            })
            
    except Exception as e:
        logger.error(f"Error updating profile image: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while updating your profile image'
        })

# Address Management Routes
@app.route('/address/add', methods=['POST'])
def add_address():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
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
        
        # If this is the first address, make it default
        existing_addresses = list(mongo.db.addresses.find({'user_id': session['user_id']}))
        if not existing_addresses:
            address['is_default'] = True
        
        mongo.db.addresses.insert_one(address)
        flash('Address added successfully', 'success')
        
    except Exception as e:
        logger.error(f"Error adding address: {str(e)}")
        flash('Error adding address', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/address/<address_id>')
def get_address(address_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        address = mongo.db.addresses.find_one({
            '_id': ObjectId(address_id),
            'user_id': session['user_id']
        })
        
        if address:
            address['_id'] = str(address['_id'])
            return jsonify(address)
        return jsonify({'error': 'Address not found'}), 404
        
    except Exception as e:
        logger.error(f"Error fetching address: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/address/<address_id>/edit', methods=['POST'])
def edit_address(address_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        update_data = {
            'name': request.form.get('name'),
            'address': request.form.get('address'),
            'city': request.form.get('city'),
            'state': request.form.get('state'),
            'zip_code': request.form.get('zip_code'),
            'country': request.form.get('country')
        }
        
        result = mongo.db.addresses.update_one(
            {
                '_id': ObjectId(address_id),
                'user_id': session['user_id']
            },
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            flash('Address updated successfully', 'success')
        else:
            flash('No changes were made to the address', 'info')
            
    except Exception as e:
        logger.error(f"Error updating address: {str(e)}")
        flash('Error updating address', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/address/<address_id>/delete', methods=['POST'])
def delete_address(address_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        # Check if this is the default address
        address = mongo.db.addresses.find_one({
            '_id': ObjectId(address_id),
            'user_id': session['user_id']
        })
        
        if address and address.get('is_default'):
            # If deleting default address, make another address default if available
            other_address = mongo.db.addresses.find_one({
                'user_id': session['user_id'],
                '_id': {'$ne': ObjectId(address_id)}
            })
            if other_address:
                mongo.db.addresses.update_one(
                    {'_id': other_address['_id']},
                    {'$set': {'is_default': True}}
                )
        
        result = mongo.db.addresses.delete_one({
            '_id': ObjectId(address_id),
            'user_id': session['user_id']
        })
        
        if result.deleted_count > 0:
            return jsonify({'success': True})
        return jsonify({'error': 'Address not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting address: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/address/<address_id>/set-default', methods=['POST'])
def set_default_address(address_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        # First, remove default status from all addresses
        mongo.db.addresses.update_many(
            {'user_id': session['user_id']},
            {'$set': {'is_default': False}}
        )
        
        # Then set the selected address as default
        result = mongo.db.addresses.update_one(
            {
                '_id': ObjectId(address_id),
                'user_id': session['user_id']
            },
            {'$set': {'is_default': True}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        return jsonify({'error': 'Address not found'}), 404
    except Exception as e:
        logger.error(f"Error setting default address: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/newsletter/subscribe', methods=['POST'])
def subscribe_newsletter():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({
                'success': False,
                'message': 'Please enter a valid email address'
            })
        
        # Check if email is already subscribed
        existing_subscriber = mongo.db.newsletter_subscribers.find_one({'email': email})
        if existing_subscriber:
            return jsonify({
                'success': False,
                'message': 'This email is already subscribed to our newsletter'
            })
        
        # Create new subscriber
        subscriber = {
            'email': email,
            'subscribed_at': datetime.now(),
            'status': 'active',
            'unsubscribe_token': bcrypt.hashpw(os.urandom(24), bcrypt.gensalt()).decode('utf-8')
        }
        
        mongo.db.newsletter_subscribers.insert_one(subscriber)
        
        return jsonify({
            'success': True,
            'message': 'Thank you for subscribing to our newsletter!'
        })
        
    except Exception as e:
        logger.error(f"Error subscribing to newsletter: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred. Please try again later.'
        })

@app.route('/newsletter/unsubscribe/<token>')
def unsubscribe_newsletter(token):
    try:
        # Find subscriber by token
        subscriber = mongo.db.newsletter_subscribers.find_one({'unsubscribe_token': token})
        if not subscriber:
            flash('Invalid unsubscribe link', 'danger')
            return redirect(url_for('index'))
        
        # Update subscriber status
        mongo.db.newsletter_subscribers.update_one(
            {'_id': subscriber['_id']},
            {'$set': {'status': 'unsubscribed', 'unsubscribed_at': datetime.now()}}
        )
        
        flash('You have been successfully unsubscribed from our newsletter', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error unsubscribing from newsletter: {str(e)}")
        flash('An error occurred while unsubscribing', 'danger')
        return redirect(url_for('index'))

# Admin Newsletter Management Routes
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
        
        # Get active subscribers
        subscribers = list(mongo.db.newsletter_subscribers.find({'status': 'active'}))
        
        # In a production environment, you would:
        # 1. Queue the emails for sending
        # 2. Use a proper email service (like SendGrid, Mailgun, etc.)
        # 3. Track email delivery and opens
        
        # For now, we'll just log the action
        logger.info(f"Newsletter '{subject}' would be sent to {len(subscribers)} subscribers")
        
        # Create newsletter record
        newsletter = {
            'subject': subject,
            'content': content,
            'sent_at': datetime.now(),
            'sent_to': len(subscribers),
            'status': 'sent'
        }
        
        mongo.db.newsletters.insert_one(newsletter)
        
        flash(f'Newsletter sent to {len(subscribers)} subscribers', 'success')
        return redirect(url_for('admin_newsletter'))
        
    except Exception as e:
        logger.error(f"Error sending newsletter: {str(e)}")
        flash('Error sending newsletter', 'danger')
        return redirect(url_for('admin_newsletter'))

@app.route('/admin/newsletter/subscribers/export')
@admin_required
def export_subscribers():
    try:
        subscribers = list(mongo.db.newsletter_subscribers.find(
            {'status': 'active'},
            {'email': 1, 'subscribed_at': 1, '_id': 0}
        ).sort('subscribed_at', -1))
        
        # Create CSV
        output = "Email,Subscribed Date\n"
        for subscriber in subscribers:
            output += f"{subscriber['email']},{subscriber['subscribed_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        return Response(
            output,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=subscribers.csv'}
        )
        
    except Exception as e:
        logger.error(f"Error exporting subscribers: {str(e)}")
        flash('Error exporting subscribers', 'danger')
        return redirect(url_for('admin_newsletter'))

@app.route('/profile/password/update', methods=['POST'])
def update_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate input
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('settings'))
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('settings'))
        
        # Get user and verify current password
        user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
        if not user or not bcrypt.checkpw(current_password.encode('utf-8'), user['password']):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('settings'))
        
        # Hash new password and update
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'password': hashed_password}}
        )
        
        flash('Password updated successfully', 'success')
        return redirect(url_for('settings'))
        
    except Exception as e:
        logger.error(f"Error updating password: {str(e)}")
        flash('An error occurred while updating your password', 'danger')
        return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(debug=True) 