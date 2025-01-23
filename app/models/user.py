from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, user_id, username, email, role, status, phone=None, address=None, price=None, notification=None):
        self.id = user_id
        self.username = username
        self.email = email
        self.phone = phone
        self.address = address
        self.role = role
        self.status = status
        self.price = price
        self.notification = notification

    def get_id(self):
        return self.id