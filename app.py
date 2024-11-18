from flask import Flask, render_template, redirect, url_for, flash, request, session
from config import Config 
from Solomon import SolomonVRP
from flask_migrate import Migrate
from extensions import db
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from geopy.geocoders import Nominatim
import pandas as pd
from datetime import datetime
from models.route import Package, CreatedRoutes, User

app = Flask(__name__)
app.config.from_object(Config)
geolocator = Nominatim(user_agent="geoapp")
login_manager = LoginManager(app)
login_manager.login_view = "login" 
routes = []


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
    disproute_names = db.session.query(CreatedRoutes.route).filter_by(user_id=current_user.id).distinct().all()
    disproute_names = [route[0] for route in disproute_names]
    return render_template("dashboard.html", routes=route_names, disproutes =  disproute_names)



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
        CreatedRoutes.query.filter_by(route=route_name, user_id=current_user.id).delete()
        
        # Add new routes
        for route in routes:
            for stop in route:
                created_route = CreatedRoutes(
                    package_id=stop["package_id"],
                    courier=stop["courier"],
                    order=stop["order"],
                    route=stop["route"],
                    planned_arrival=stop.get("planned_arrival"),
                    user_id=current_user.id,
                    depot = depot
                )
                db.session.add(created_route)
                
        db.session.commit()
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"Error processing routes: {e}", "danger")
        return redirect(url_for("dashboard"))
     

# Logout route
@app.route("/display_route", methods=["GET", "POST"])
@login_required
def display_route():
    try:
        disproute_names = db.session.query(CreatedRoutes.route).filter_by(user_id=current_user.id).distinct().all()
        disproute_names = [route[0] for route in disproute_names]
        created_routes = []
        if request.method == "POST":
            route_name = request.form['disproute']
            depot_info = CreatedRoutes.query.filter_by(
                    user_id=current_user.id, 
                    route=route_name
                ).first()
            depot_lat, depot_long = geocode_address(depot_info.depot, 0)
            if route_name:
                created_routes = db.session.query(
                    CreatedRoutes.package_id,
                    CreatedRoutes.courier,
                    CreatedRoutes.order,
                    CreatedRoutes.planned_arrival,
                    CreatedRoutes.depot,
                    Package.client,
                    Package.address,
                    Package.latitude,
                    Package.longitude,
                    Package.time_from,
                    Package.time_to
                ).join(Package, CreatedRoutes.package_id == Package.package_id) \
                .filter(Package.user_id == current_user.id, CreatedRoutes.route == route_name) \
                .order_by(CreatedRoutes.courier.asc(), CreatedRoutes.order.asc()) \
                .all()
                created_routes = [
                        {
                            'package_id': route.package_id,
                            'courier': route.courier,
                            'order': route.order,
                            'planned_arrival': route.planned_arrival,
                            'depot': route.depot,
                            'depot_lat': depot_lat,
                            'depot_long': depot_long,
                            'client': route.client,
                            'address': route.address,
                            'latitude': route.latitude,
                            'longitude': route.longitude,
                            'time_from': route.time_from,
                            'time_to': route.time_to
                        } for route in created_routes
                    ]
        return render_template("display_route.html", created_routes=created_routes, disproutes =  disproute_names)
                


    except Exception as e:
        flash(f"Error displaying routes: {e}", "danger")
        return redirect(url_for("dashboard"))
    
@app.route("/edit_packages", methods=["GET", "POST"])
@login_required
def edit_packages():
    try:
        disproute_names = db.session.query(Package.route).filter_by(user_id=current_user.id).distinct().all()
        disproute_names = [route[0] for route in disproute_names]
        last_selected_route = session.get('last_selected_route', None)
        created_routes=[]
        disp_package_id = []
        if request.method == "POST":
            route_name = request.form['disproute']
            session['last_selected_route'] = route_name
            last_selected_route = route_name
            created_routes = Package.query.filter_by(user_id=current_user.id, route = route_name).all()
            disp_package_id = db.session.query(Package.package_id).filter_by(user_id=current_user.id, route = route_name).distinct().all()
            disp_package_id = [package[0] for package in disp_package_id]
        elif last_selected_route:
            created_routes = Package.query.filter_by(user_id=current_user.id, route=last_selected_route).all()
            disp_package_id = db.session.query(Package.package_id).filter_by(user_id=current_user.id, route = last_selected_route).distinct().all()
            disp_package_id = [package[0] for package in disp_package_id]
        return render_template("edit_packages.html", disproutes = disproute_names, created_routes = created_routes , last_selected_route = last_selected_route, disp_package_id = disp_package_id)

    except Exception as e:
        flash(f"Error Retriving package: {e}", "danger")
        return redirect(url_for("edit_packages"))
    
@app.route("/add_package", methods=["POST"])
@login_required
def add_package():
    try:
        if request.method == "POST":
            package_id = request.form['package_id']
            client = request.form['client']
            address = request.form['address']
            time_from = request.form['time_from']
            time_to = request.form['time_to']
            route_name = request.form['route']
            latitude, longitude = geocode_address(address,0)
            print(package_id,client,address,time_from,time_to, route_name, longitude, latitude)
            new_package = Package(
                        package_id=package_id,
                        client=client,
                        address=address,
                        time_from=time_from,
                        time_to=time_to,
                        latitude=latitude,
                        longitude=longitude,
                        user_id=current_user.id,  # Associate package with the logged-in user
                        route = route_name
                    )
            db.session.add(new_package)
            db.session.commit()
            session['last_selected_route'] = route_name
            return redirect(url_for("edit_packages"))


    except Exception as e:
        flash(f"Error adding package: {e}", "danger")
        return redirect(url_for("edit_packages"))
    
@app.route("/remove_package", methods=["POST"])
@login_required
def remove_package():
    try:
        if request.method == "POST":
            package_id = request.form['disp_package']
            route_name = request.form['route_id']
            print(route_name, package_id)
            Package.query.filter_by(route=route_name, user_id=current_user.id, package_id = package_id).delete()
            db.session.commit()
            session['last_selected_route'] = route_name
            return redirect(url_for("edit_packages"))


    except Exception as e:
        flash(f"Error Removing package: {e}", "danger")
        return redirect(url_for("edit_packages"))
    
@app.route("/update_package", methods=["POST"])
@login_required
def update_package():
    try:
        if request.method == "POST":
            package_id = request.form.get('disp_package')
            client = request.form.get('client') or None
            address = request.form.get('address') or None
            time_from = request.form.get('time_from') or None
            time_to = request.form.get('time_to') or None
            route_name = request.form.get('route') or None

            # Only geocode if the address is provided
            if address:
                latitude, longitude = geocode_address(address, 0)
            else:
                latitude, longitude = None, None

            print(package_id, client, address, time_from, time_to, route_name, longitude, latitude)

            # Retrieve the package from the database if it already exists, or create a new one
            package = Package.query.filter_by(package_id=package_id, user_id=current_user.id).first()
            # New package associated with the current user

            # Update only the fields that are present
            if package_id is not None:
                package.package_id = package_id
            if client is not None:
                package.client = client
            if address is not None:
                package.address = address
            if time_from is not None:
                package.time_from = time_from
            if time_to is not None:
                package.time_to = time_to
            if latitude is not None and longitude is not None:
                package.latitude = latitude
                package.longitude = longitude
            if route_name is not None:
                package.route = route_name

            # Add or update the package in the session and commit
            db.session.add(package)
            db.session.commit()

            # Store last selected route in session if route_name was provided
            if route_name:
                session['last_selected_route'] = route_name

        return redirect(url_for("edit_packages"))



    except Exception as e:
        flash(f"Error updating package: {e}", "danger")
        return redirect(url_for("edit_packages"))


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

# Run the app
if __name__ == "__main__":
    app.run(debug=True)