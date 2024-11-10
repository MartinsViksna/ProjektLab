import pandas as pd
from geopy.distance import geodesic
from collections import deque

# Helper function to calculate distance between two points (latitude, longitude)
def calculate_distance(point1, point2):
    return geodesic(point1, point2).km

# Helper function to create a distance matrix between all delivery points
def create_distance_matrix(locations):
    n = len(locations)
    dist_matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_matrix[i][j] = calculate_distance(locations[i], locations[j])
    return dist_matrix

# Define the Solomon VRP solver class
class SolomonVRP:
    def __init__(self, delivery_data, couriers, depot_location):
        self.delivery_data = delivery_data  # DataFrame with time windows, latitude, longitude, demand
        self.couriers = couriers  # Number of couriers available
        self.depot_location = depot_location  # Depot coordinates
        self.distance_matrix = create_distance_matrix(self.delivery_data[['latitude', 'longitude']].values)

    def create_routes(self):
        routes = [[] for _ in range(self.couriers)]  # List of routes for each courier
        total_route_costs = [0] * self.couriers  # Track the total cost (distance) of each courier's route
        
        # Sort delivery locations based on time windows or another heuristic (e.g., closest to depot)
        delivery_points = self.delivery_data.sort_values(by=['time_from'])

        for idx, delivery in delivery_points.iterrows():
            best_courier = None
            best_route_cost_increase = float('inf')
            
            # Check available couriers and choose the best one based on the smallest route cost increase
            for courier in range(self.couriers):
                route_cost = self.calculate_route_cost(routes[courier], delivery)
                new_route_cost = total_route_costs[courier] + route_cost
                
                # Choose the courier whose route will increase the least
                if new_route_cost < best_route_cost_increase:
                    best_route_cost_increase = new_route_cost
                    best_courier = courier
            
            # Assign the delivery point (latitude, longitude) to the best courier's route
            routes[best_courier].append((delivery['latitude'], delivery['longitude']))
            total_route_costs[best_courier] += best_route_cost_increase  # Update the total cost of the route
        
        return routes

    def calculate_route_cost(self, route, delivery):
        # If the route is empty, return the distance from the depot to the first delivery point
        if not route:
            return calculate_distance(self.depot_location, (delivery['latitude'], delivery['longitude']))
        
        # Get the last location from the route (last delivery point)
        last_location = route[-1]
        
        # Calculate the distance from the last location to the new delivery point
        distance = calculate_distance(last_location, (delivery['latitude'], delivery['longitude']))
        
        return distance

# Example usage:

