from extensions import db
from flask_login import UserMixin
class Package(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.String(50), nullable=False)
    client = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    time_from = db.Column(db.String(50), nullable=False)
    time_to = db.Column(db.String(50), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    route= db.Column(db.String(255), nullable=False)

class CreatedRoutes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.String(255), db.ForeignKey('package.package_id'), nullable=False)
    courier = db.Column(db.Integer, nullable=False)
    order = db.Column(db.Integer, nullable=False)
    route = db.Column(db.String(255), db.ForeignKey('package.route'), nullable=False)
    planned_arrival = db.Column(db.Integer)
    depot = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    def __repr__(self):
        return f"<User {self.username}>"

