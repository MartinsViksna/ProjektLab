from extensions import db

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
    route= db.Column(db.String(50), nullable=False)

class CreatedRoutes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.String(50), db.ForeignKey('package.package_id'), nullable=False)
    courier = db.Column(db.Integer, nullable=False)
    order = db.Column(db.Integer, nullable=False)
    route = db.Column(db.String(50), db.ForeignKey('package.route'), nullable=False)
    planned_arrival = db.Column(db.Integer)