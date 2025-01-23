from flask import Flask
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from haversine import haversine
from app.models.user import User

mongo = PyMongo()
bcrypt = Bcrypt()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    #configuration
    app.config['SECRET_KEY'] = 'your-secret-key'
    app.config['MONGO_URI'] = 'mongodb://localhost:27017/gas_market'

    mongo.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    
    # Create the index after the app is initialized
    with app.app_context():
        mongo.db.users.create_index({"location": "2dsphere"})

    from app.routes.auth import auth_bp
    from app.routes.buyer import buyer_bp
    from app.routes.seller import seller_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(buyer_bp, url_prefix='/buyer')
    app.register_blueprint(seller_bp, url_prefix='/seller')

    return app



geolocator = Nominatim(user_agent="gas_app")

def geocode_with_retry(address, retries=3, timeout=10):
    """Geocode an address with retry logic."""
    for attempt in range(retries):
        try:
            location = geolocator.geocode(address, timeout=timeout)
            if location:
                return location
        except GeocoderTimedOut:
            if attempt < retries - 1:
                continue
    return None

def validate_request(data, fields):
    """Validate if the required fields exist in the request data."""
    for field in fields:
        if field not in data or not data[field]:
            return False, f"Missing or invalid field: {field}"
    return True, None

def serialize_document(doc):
    """Convert MongoDB document to JSON-serializable format."""
    doc["_id"] = str(doc["_id"])
    return doc


@login_manager.user_loader
def load_user(user_id):
    # print(f"Loading user with user_id: {user_id}")  # Debug statement
    user_data = mongo.db.users.find_one({'user_id': user_id})
    if user_data:
        # print(f"User data found: {user_data}")  # Debug statement
        return User(
            user_id=str(user_data['user_id']),
            username=user_data['username'],
            email=user_data['email'],
            phone=user_data.get('phone'),
            address=user_data.get('address'),
            role=user_data['role'],
            status=user_data['status'],
            price=user_data.get('price'),
            notification=user_data.get('notification')
        )
    
    return None