from flask_login import current_user, login_required, logout_user
from haversine import haversine
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import mongo, geocode_with_retry
import uuid

buyer_bp = Blueprint('buyer', __name__)

@buyer_bp.route("/buyer_dashboard")
def buyer_dashboard():
    buyer_id = current_user.get_id()
    orders = list(mongo.db.orders.find({"buyer_id": buyer_id}))
    order_count = mongo.db.orders.count_documents({"buyer_id": buyer_id})
    order_pending = mongo.db.orders.count_documents({"buyer_id": buyer_id, "order_status": "Pending"})
    order_rejected = mongo.db.orders.count_documents({"buyer_id": buyer_id, "order_status": "Rejected"})
    order_delivered = mongo.db.orders.count_documents({"buyer_id": buyer_id, "order_status": "Delivered"})
    return render_template("buyer_dashboard.html", user=current_user, orders=orders, order_count=order_count, order_pending=order_pending, order_delivered=order_delivered, order_rejected=order_rejected)

@buyer_bp.route("/edit_user_profile", methods=['GET', 'POST'])
@login_required
def edit_user_profile():
    if request.method == "POST":
        # Get the address from the form
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')

        # Get the current user's data from the database
        user_collection = mongo.db.users  # Replace 'users' with your actual collection name
        current_user_data = user_collection.find_one({"user_id": current_user.get_id()})

        if not current_user_data:
            flash("User not found. Please log in again.", "danger")
            return redirect(url_for("auth.login"))

        # Check if the username is being changed and if it already exists
        if name != current_user_data.get("username") and user_collection.find_one({"username": name}):
            flash("Username already exists!", "danger")
            return redirect(url_for("buyer.edit_user_profile"))

        # Check if the email is being changed and if it already exists
        if email != current_user_data.get("email") and user_collection.find_one({"email": email}):
            flash("Email already exists!", "danger")
            return redirect(url_for("buyer.edit_user_profile"))

        # Validate input
        if not (name.strip() and email.strip() and phone.strip()):
            flash("All fields are required!", "danger")
            return redirect(url_for("buyer.edit_user_profile"))

        # Update the user's profile in the database
        user_collection.update_one(
            {"user_id": current_user.get_id()},  # Find the current user's document
            {"$set": {
                    "username": name,
                    "email": email,
                    "phone": phone,                    
            }}            
        )

        flash("Profile updated successfully!", "success")
        return redirect(url_for("buyer.buyer_dashboard"))

    return render_template("edit_buyer.html", user=current_user)

@buyer_bp.route('/search', methods=['GET', 'POST'])
def search_sellers():
    if request.method == 'GET':
        return render_template("search_seller.html", sellers=[])

    data = request.form
    address = data.get("address")

    try:
        max_distance_km = float(data.get("radius", 0))
    except ValueError:
        return jsonify({"error": "Invalid radius value."}), 400 # Convert radius to float

    sort_by = data.get("sort_by", "distance")  # Default to 'distance' if not provided

    # Geocode Address
    location = geocode_with_retry(address)
    if not location:
        flash("Geocoding failed, please try again.")
        return render_template("search.html", sellers=[])

    latitude = location.latitude
    longitude = location.longitude

    # Fetch only sellers from the database
    sellers = list(mongo.db.users.find({"role": "seller"}))  # Query sellers only
    results = []

    for seller in sellers:
        # Ensure location exists and has valid coordinates
        if "location" not in seller or "coordinates" not in seller["location"]:
            continue

        # Extract coordinates
        try:
            seller_lon, seller_lat = seller["location"]["coordinates"]  # MongoDB stores as [longitude, latitude]
        except ValueError:
            continue

        # Calculate the distance
        distance = haversine((latitude, longitude), (seller_lat, seller_lon))

        # Check if within the max distance
        if distance <= max_distance_km:
            # Fetch the seller's rating from the sellers collection
            seller_id = seller.get("user_id", "unknown")
            seller_details = mongo.db.sellers.find_one({"seller_id": seller_id})
            seller_rating = seller_details.get("average_rating", "N/A") if seller_details else "N/A"

            seller_data = {
                "name": seller.get("username", "Unknown"),
                "address": seller.get("address", "Unknown"),
                "price": seller.get("price", "N/A"),  # Default to "N/A" if price is missing
                "distance": round(distance, 2),
                "seller_id": seller_id,
                "buyer_id": current_user.get_id(),
                "rating": int(seller_rating)
            }
            results.append(seller_data)

    # Sort results
    if sort_by == "distance":
        results.sort(key=lambda x: x["distance"])
    elif sort_by == "price":
        results.sort(key=lambda x: x["price"])

    return render_template("search_seller.html", sellers=results, user=current_user)

# Endpoint to place an order
@buyer_bp.route('/order', methods=['GET', 'POST'])
def place_order():
    if request.method == 'GET':
        seller_id = request.args.get('seller_id')
        buyer_id = request.args.get('buyer_id')
        price = request.args.get('price')
        return render_template("order.html", seller_id=seller_id, buyer_id=buyer_id, price=price, user=current_user)
    
    
    orders_collection = mongo.db.orders
    if request.method == "POST":
        try:            
            # Parse JSON data from request
            data = request.form

            # Extract seller_id from the form data
            seller_id = data['seller_id']
            if not seller_id:
                return jsonify({"error": "Seller ID is required."}), 400
            
            buyer_id = data['buyer_id']
            if not buyer_id:
                return jsonify({"error": "Buyer ID is required."}), 400
            
            required_fields = ['buyerName', 'buyerPhone', 'buyerEmail', 'deliveryAddress', 
                            'quantity', 'deliveryDate', 'paymentMethod']
            
            # Validate required fields
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            if missing_fields:
                return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400
            
            # Additional validation
            try:
                quantity = float(data['quantity'])
                if quantity <= 0:
                    return jsonify({"error": "Quantity must be greater than 0."}), 400
            except ValueError:
                return jsonify({"error": "Quantity must be a valid number."}), 400

            # # Validate delivery date (future date)
            try:
                delivery_date = datetime.strptime(data["deliveryDate"], "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

            if delivery_date.date() < datetime.now().date():
                return jsonify({"error": "Delivery date must be today or in the future."}), 400
            
            # Prepare order document
            order = {
                "order_id": str(uuid.uuid4()),
                "seller_id": seller_id,
                "buyer_id": buyer_id,
                "buyer_name": data['buyerName'],
                "buyer_phone": data['buyerPhone'],
                "buyer_email": data['buyerEmail'],
                "delivery_address": data['deliveryAddress'],
                "quantity": quantity,
                "price": int(data['price']),
                "delivery_date": delivery_date.isoformat(),
                "payment_method": data['paymentMethod'],
                "additional_notes": data.get('additionalNotes', ''),
                "order_status": "Pending",
                "rated": False,
                "status_history": [
                    {
                        "status": "Ordered at",
                        "timestamp": datetime.now()
                    }
                ],
                "hidden_for_seller": False,
                "created_at": datetime.now(),
            }

            # Save order to MongoDB
            result = orders_collection.insert_one(order)
            flash("Order placed successfully!")
            return redirect(url_for("buyer.buyer_dashboard"))

        except Exception as e:
            return jsonify({"error": "An error occurred while placing the order.", "details": str(e)}), 500
        
@buyer_bp.route("/confirm_delivery", methods=["POST"])
def confirm_delivery():
    order_id = request.form.get("order_id")

    if not order_id:
        flash("Order ID is missing!", "danger")
        return redirect(url_for("buyer.my_orders"))

    # Update the order status to Delivered
    result = mongo.db.orders.update_one(
        {"order_id": order_id},
        {
            "$set": {"order_status": "Completed"},
            "$push": {
                "status_history": {
                    "status": "Completed",
                    "timestamp": datetime.now()
                }
            }
        }
    )
    if result.modified_count > 0:
        flash("Delivery confirmed successfully!", "success")
    else:
        flash("Failed to confirm delivery.", "danger")

    return redirect(url_for("buyer.my_orders"))

@buyer_bp.route("/my_orders")
def my_orders():
    buyer_id = current_user.get_id()
    orders = list(mongo.db.orders.find({"buyer_id": buyer_id}))
    return render_template("my_orders.html", orders=orders)

@buyer_bp.route('/rate_seller', methods=['GET', 'POST'])
def rate_seller():
    if request.method == 'GET':
        seller_id = request.args.get('seller_id')
        buyer_id = request.args.get('buyer_id')
        order_id = request.args.get('order_id')
        return render_template("rate_seller.html", seller_id=seller_id, buyer_id=buyer_id, order_id=order_id)
    
    if request.method == 'POST':
        data = request.form
        seller_id = data['seller_id']
        buyer_id = data['buyer_id']
        order_id = data['order_id']
        rating = int(data.get('rating', 5))
        review = data.get('review', '').strip()

        if not rating or not review or not seller_id or not buyer_id:
            flash("All fields are required.")
            return redirect(request.referrer)


        # Add rating to the seller's record
        try:
            mongo.db.sellers.update_one(
                {"seller_id": seller_id},
                {
                    "$push": {
                        "ratings": {
                            "buyer_id": buyer_id,
                            "rating": rating,
                            "review": review,
                            "created_at": datetime.now()
                        }
                    },
                    "$set": {
                        "average_rating": calculate_average_rating(seller_id, 'sellers')
                    }
                },
                upsert=True  # Create document if it doesn't exist
            )

            # **Mark the order as rated**
            mongo.db.orders.update_one(
                {"order_id": order_id}, {"$set": {"rated": True}}
            )

            flash("Thank you for your feedback!")
        except Exception as e:
            flash("An error occurred while submitting your rating.")
    return redirect(url_for("buyer.buyer_dashboard"))

def calculate_average_rating(entity_id, collection):    
    
    # Determine the query field
    query_field = "seller_id" if collection == 'sellers' else "buyer_id"
    
    # Retrieve the document
    entity = mongo.db[collection].find_one({query_field: entity_id})
    
    if not entity:  # Handle case where no entity is found
        return 0  # Default average rating
    
    ratings = entity.get('ratings', [])
    if not ratings:
        return 5  # Default average rating if no ratings exist

    # Calculate the average rating
    average_rating = round(sum(r['rating'] for r in ratings) / len(ratings), 1)
    print(average_rating)
    return average_rating 


@buyer_bp.route("/cancel_order", methods=["POST"])
def cancel_order():
    order_id = request.form.get("order_id")
    # action = request.form.get("action")


    # Update in MongoDB
    result = mongo.db.orders.update_one(
        {"order_id": order_id},
        {
            "$set": {"order_status": "Cancelled"},
            "$push": {
                "status_history": {
                    "status": "Cancelled", 
                    "timestamp": datetime.now()
                }
            }
        }
    )
    if result.modified_count > 0:
        flash(f"Order cancelled!", "success")
    else:
        flash("Failed to update order status.", "danger")

    return redirect(url_for("buyer.my_orders"))

@buyer_bp.route('/receipt')
def generate_receipt():    
    order_id = request.args.get("order_id")
    seller_id = request.args.get("seller_id")

    seller = mongo.db.users.find_one({"user_id": seller_id})
    if not seller:
        return "Seller not found", 404
    seller_name = seller.get("username", "Unknown Seller")
    
    order = mongo.db.orders.find_one({"order_id": order_id})
    if not order:
        return "Order not found", 404
    
    # Extract timestamp for "Ordered at" status
    ordered_timestamp = None
    for status in order.get("status_history", []):
        if status.get("status") == "Ordered at":
            ordered_timestamp = status.get("timestamp")
            break  # Stop after finding the first occurrence

    # Calculate total price dynamically
    total_price = order["quantity"] * order["price"]
    
    return render_template('receipt.html', order=order, seller_name=seller_name, total_price=total_price)


@buyer_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
