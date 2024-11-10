from extensions import db
from datetime import datetime

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
    date= db.Column(db.Date, default=datetime.utcnow().date)
    user = db.relationship('User', backref=db.backref('packages', lazy=True))
    