from flask import Blueprint, request, jsonify, url_for, render_template, redirect, flash, session
from flask_login import login_user, current_user, UserMixin
from app import User, mongo, bcrypt, geocode_with_retry, validate_request
import uuid
from geopy.distance import geodesic
from haversine import haversine
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

# Buyer Authentication
@auth_bp.route('/register/buyer', methods=['GET', 'POST'])
def register_buyer():
    if request.method == 'POST':
        try:
            if request.content_type == "application/json":
                data = request.get_json()
                username = data.get("username")
                password = data.get("password")
                email = request.get("email")
                phone = request.get("phone")
                address = request.get("address")
            else:
                # Fallback for form submissions
                username = request.form.get("username")
                password = request.form.get("password")
                email = request.form.get("email")
                phone = request.form.get("phone")
                address = request.form.get("address")
               
            # Input validation
            if not username or not password:
                return jsonify({"error": "Username and password are required"})

            # Check if the username already exists
            if mongo.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
                return jsonify({"error": "Username or email already exists"}), 400
            
            
            # Hash the password before saving
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            
            # Insert the new user into the database
            mongo.db.users.insert_one({
                "user_id": str(uuid.uuid4()),
                "username": username,
                "email": email, 
                "password": hashed_password,
                "phone": phone,
                "address": address, 
                "role": "buyer",
                "status": "approved"
            })
            # Return a success message
            return jsonify({"message": "Registration successful! Redirecting to login...", "redirect": url_for("auth.login")}), 200
        
        except Exception as e:
            # Log the error for debugging
            print(f"Error during registration: {e}")
            return jsonify({'error': 'An unexpected error occurred. Please try again later.'}), 500
        
    return render_template("register_buyer.html")

# Seller Authentication
@auth_bp.route('/register/seller', methods=['GET', 'POST'])
def register_seller():
    if request.method == 'POST':
        try:
            # Validate content type
            if request.content_type == "application/json":
                data = request.get_json()
            elif request.form:
                data = request.form
            else:
                return jsonify({"error": "Invalid content type"}), 400

            # Extract fields
            username = data.get("username")
            email = data.get("email")
            password = data.get("password")
            phone = data.get("phone")
            address = data.get("address")

            # Input validation
            if not username or not password or not email:
                return jsonify({"error": "Username, email, and password are required"}), 400
            if len(password) < 8:
                return jsonify({"error": "Password must be at least 8 characters long"}), 400
            
            # Check if the user already exists
            if mongo.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
                return jsonify({"error": "Username or email already exists"}), 400

            # Hash the password
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

            # Insert the user
            mongo.db.users.insert_one({
                "user_id": str(uuid.uuid4()),
                "username": username,
                "email": email,
                "password": hashed_password,
                "phone": phone,
                "address": address,
                "role": "seller",
                "status": "pending"
            })

            # Return a success message for AJAX
            if request.content_type == "application/json":
                return jsonify({"message": "Registration successful!", "redirect": url_for("auth.login")}), 200

            # For regular form submissions, flash a message and redirect
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("auth.login"))

        except mongo.errors.DuplicateKeyError:
            return jsonify({"error": "A user with this username or email already exists."}), 400
        except Exception as e:
            print(f"Error during registration: {e}")
            return jsonify({"error": "An unexpected error occurred. Please try again later."}), 500
    return render_template("register_seller.html")

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            # Retrieve credentials
            username = request.form.get('username')
            password = request.form.get('password')

            # Input validation
            if not username or not password:
                return jsonify({'error': 'Username and password are required'}), 400

            # Find user in MongoDB
            user_data = mongo.db.users.find_one({'username': username})
            if not user_data:
                flash("User not found", "danger")
                return redirect(url_for("auth.login"))

            # Verify password
            if not bcrypt.check_password_hash(user_data['password'], password):
                flash('Invalid credentials', 'danger')
                return redirect(url_for('auth.login'))
           
            print(f"User data: {user_data}")  # Debug statement

            # Create a User object and log in
            user = User(
                user_id=user_data['user_id'],
                username=user_data['username'],
                role=user_data['role'],
                status=user_data['status'],
                email=user_data.get('email')
            )
            print(f"Logging in user: {vars(user)}")  # Debug statement
            login_user(user)

            # Redirect based on role
            if user.role == 'seller':
                return redirect(url_for('seller.seller_dashboard'))
            elif user.role == 'buyer':
                return redirect(url_for('buyer.buyer_dashboard'))
            elif user.role == "admin":
                return redirect(url_for("admin.admin_dashboard"))
            
        except Exception as e:
            # Log the error for debugging
            print(f"Error during login: {e}")
            return jsonify({'error': 'An unexpected error occurred'}), 500
    return render_template('login.html')