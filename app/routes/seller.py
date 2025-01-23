from flask import Blueprint, request, flash, redirect, url_for, jsonify, render_template
from app import mongo
from flask_login import current_user, login_required, logout_user
from datetime import datetime

seller_bp = Blueprint('seller', __name__)

@seller_bp.route("/seller_dashboard")
def seller_dashboard():
    user = current_user
    seller_id = current_user.get_id()
    orders = list(mongo.db.orders.find({"seller_id": seller_id}))
    order_count = mongo.db.orders.count_documents({"seller_id": seller_id})
    order_pending = mongo.db.orders.count_documents({"seller_id": seller_id, "order_status": "Pending"})
    order_delivered = mongo.db.orders.count_documents({"seller_id": seller_id, "order_status": "Delivered"})
    sellers_rating = mongo.db.sellers.find_one({"seller_id": seller_id})
    return render_template("seller_dashboard.html", user=user, orders=orders, order_count=order_count, order_pending=order_pending, order_delivered=order_delivered, sellers_rating=sellers_rating)

@seller_bp.route("/edit_profile")
def edit_profile():
    return render_template("edit_seller.html")

@seller_bp.route("/view_orders")
def view_orders():
    seller_id = current_user.get_id()
    orders = list(mongo.db.orders.find({"seller_id": seller_id, "hidden_for_seller": False}))
    return render_template("view_orders.html", orders=orders)

@seller_bp.route("/view_order_detail", methods=["POST"])
def view_order_detail():
    seller_id = current_user.get_id()
    order_id = request.form.get("order_id")
    order = mongo.db.orders.find_one({"order_id": order_id, "seller_id": seller_id})
    
    if not order:
        flash("Order not found or unauthorized access.", "danger")
        return redirect(url_for("seller.view_orders"))
    
    return render_template("view_order_detail.html", order=order)


@seller_bp.route("/update_order_status", methods=["POST"])
def update_order_status():
    order_id = request.form.get("order_id")
    action = request.form.get("action")

    # Update order status based on the seller's action
    if action == "accept":
        new_status = "Accepted"
    elif action == "reject":
        new_status = "Cancelled"
    else:
        flash("Invalid action!", "danger")
        return redirect(url_for("seller.seller_dashboard"))

    # Update in MongoDB
    result = mongo.db.orders.update_one(
        {"order_id": order_id},
        {
            "$set": {"order_status": new_status},
            "$push": {
                "status_history": {
                    "status": new_status, 
                    "timestamp": datetime.now()
                }
            }
        }
    )
    if result.modified_count > 0:
        flash(f"Order status updated to {new_status}!", "success")
    else:
        flash("Failed to update order status.", "danger")

    return redirect(url_for("seller.view_orders"))

@seller_bp.route("/mark_as_delivered", methods=["POST"])
def mark_as_delivered():
    order_id = request.form.get("order_id")

    # Update the order status to Delivered
    result = mongo.db.orders.update_one(
        {"order_id": order_id},
        {
            "$set": {"order_status": "Delivered"},
            "$push": {
                "status_history": {
                    "status": "Delivered", 
                    "timestamp": datetime.now()
                }
            }
        }
    )

    if result.modified_count > 0:
        flash("Order marked as delivered!", "success")
    else:
        flash("Failed to mark order as delivered.", "danger")

    return redirect(url_for("seller.view_orders"))


@seller_bp.route("/manage_inventory")
def manage_inventory():
    return render_template("manage_inventory.html")

@seller_bp.route("/ratings", methods=["GET"])
def view_ratings():
    """Fetch ratings and reviews for a seller"""
    seller_id = current_user.get_id()
    
    # Fetch seller data with ratings
    seller_data = mongo.db.sellers.find_one({"seller_id": seller_id}, {"ratings": 1, "average_rating": 1, "_id": 0})

    # If no ratings exist, set a default response
    if not seller_data:
        seller_data = {"average_rating": 5, "ratings": []}  # Default rating

    # Extract reviews
    reviews_list = [{"rating": r["rating"], "review": r["review"]} for r in seller_data.get("ratings", [])]

    return render_template("view_rating.html", ratings=seller_data, reviews_list=reviews_list)

@seller_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))