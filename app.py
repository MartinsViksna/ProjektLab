from flask import Flask, render_template, redirect, url_for, flash, request
from config import Config 
from Solomon import SolomonVRP
from flask_migrate import Migrate
from extensions import db
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from geopy.geocoders import Nominatim
import pandas as pd
from datetime import datetime
from models.route import Package, CreatedRoutes

app = Flask(__name__)
app.config.from_object(Config)
geolocator = Nominatim(user_agent="geoapp")
login_manager = LoginManager(app)
login_manager.login_view = "login" 
routes = []

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    def __repr__(self):
        return f"<User {self.username}>"

db.init_app(app)
migrate = Migrate(app, db)
with app.app_context():
    # Create tables if not already created
    db.create_all()


def geocode_address(address,retry):
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    elif retry<=10:
        geocode_address(address, retry+1)
    else: return None, None

# User loader function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Routes for login and register pages

# Register route
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists. Please choose another.", "danger")
            return redirect(url_for("register"))
        
        # Create new user
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))
    
    return render_template("register.html")

# Login route
@app.route("/", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')
    

# Dashboard route (protected route)
@app.route("/dashboard" , methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        file = request.files['csv_file']
        name = request.form['name']
        if file:
            try:
                # Read CSV file into pandas dataframe
                df = pd.read_csv(file)
                
                # Iterate over each row in the dataframe
                for index, row in df.iterrows():
                    # Extract data from CSV row
                    package_id = row["package id"]
                    client = row["Client"]
                    address = row["Address"]
                    time_from = row["Time from"]
                    time_to = row["Time to"]
                    
                    # Geocode the address
                    latitude, longitude = geocode_address(address,0)
                    
                    # Create new package instance
                    new_package = Package(
                        package_id=package_id,
                        client=client,
                        address=address,
                        time_from=time_from,
                        time_to=time_to,
                        latitude=latitude,
                        longitude=longitude,
                        user_id=current_user.id,  # Associate package with the logged-in user
                        route = name
                    )
                    
                    # Add to the database
                    db.session.add(new_package)
                
                # Commit changes to the database
                db.session.commit()
                flash("CSV data has been successfully uploaded and processed!", "success")
                return redirect(url_for("dashboard"))
            except Exception as e:
                flash(f"Error processing CSV file: {e}", "danger")
                return redirect(url_for("dashboard"))
            
    route_names = db.session.query(Package.route).filter_by(user_id=current_user.id).distinct().all()
    route_names = [route[0] for route in route_names]
    return render_template("dashboard.html", routes=route_names)



@app.route("/process_routes", methods=["POST"])
@login_required
def process_routes():
    try:
        # Fetch the delivery data for the current user from the database
        couriers = request.form['couriers']
        depot = request.form['depot']
        route_name = request.form['route']
        depot_lat,depot_long = geocode_address(depot,0)
        print(couriers,depot, depot_lat, depot_long)
        deliveries = Package.query.filter_by(user_id=current_user.id, route=route_name).all()
        print(deliveries)

        # Prepare the data for VRP solver
        delivery_data = pd.DataFrame([{
            'package_id': d.package_id,
            'client': d.client,
            'address': d.address,
            'latitude': d.latitude,
            'longitude': d.longitude,
            'time_from':  d.time_from,
            'time_to':  d.time_to
        } for d in deliveries])

        # Create and solve the VRP
        print(route_name)
        vrp_solver = SolomonVRP(
            delivery_data, 
            couriers, 
            (depot_lat, depot_long),
            route_name
        )
        
        routes = vrp_solver.solve()
        if not routes:
            flash("Could not find a valid solution", "danger")
            return redirect(url_for("dashboard"))
            
        # Clear existing routes for this route_name
        CreatedRoutes.query.filter_by(route=route_name).delete()
        
        # Add new routes
        for route in routes:
            for stop in route:
                created_route = CreatedRoutes(
                    package_id=stop["package_id"],
                    courier=stop["courier"],
                    order=stop["order"],
                    route=stop["route"],
                    planned_arrival=stop.get("planned_arrival")
                )
                db.session.add(created_route)
                
        db.session.commit()
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"Error processing routes: {e}", "danger")
        return redirect(url_for("dashboard"))
     

# Logout route
@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

# Run the app
if __name__ == "__main__":
    app.run(debug=True)