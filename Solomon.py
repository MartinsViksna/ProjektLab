from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from datetime import datetime
import numpy as np
import pandas as pd
import logging

class SolomonVRP:
    def __init__(self, deliveries_df, num_vehicles, depot_location, route_name):
        """
        Initialize the Solomon VRP solver
        
        Args:
            deliveries_df: DataFrame with columns [package_id, latitude, longitude, time_from, time_to]
            num_vehicles: Number of available vehicles/couriers
            depot_location: Tuple of (latitude, longitude) for the depot
            route_name: Name of the route being processed
        """
        self.deliveries = deliveries_df
        self.num_vehicles = int(num_vehicles)
        self.depot_lat, self.depot_lon = depot_location
        self.route_name = route_name
        self.locations = self._prepare_locations()
        self.time_matrix = self._create_time_matrix()
        self.time_windows = self._prepare_time_windows()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def _prepare_locations(self):
        """Prepare location coordinates including depot"""
        # Add depot as first location
        locations = [(self.depot_lat, self.depot_lon)]
        # Add delivery locations
        locations.extend(list(zip(self.deliveries['latitude'], self.deliveries['longitude'])))
        return locations
    
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the great circle distance between two points in kilometers"""
        R = 6371  # Earth's radius in kilometers
        
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        distance = R * c
        
        # Convert distance to minutes assuming average speed of 30 km/h
        # Add a small buffer to ensure feasibility
        minutes = (distance / 70) * 60
        return int(minutes + 5)  # Add 5 minutes buffer for traffic/stops
    
    def _create_time_matrix(self):
        """Create time matrix between all locations"""
        num_locations = len(self.locations)
        matrix = np.zeros((num_locations, num_locations))
        
        for i in range(num_locations):
            for j in range(num_locations):
                if i != j:
                    lat1, lon1 = self.locations[i]
                    lat2, lon2 = self.locations[j]
                    matrix[i][j] = self._haversine_distance(lat1, lon1, lat2, lon2)
        
        return matrix.astype(int)
    
    def _convert_time_to_minutes(self, time_str):
        """Convert time string (HH:MM) to minutes since midnight"""
        try:
            # Handle different time formats
            for fmt in ['%H:%M', '%H:%M:%S', '%I:%M %p']:
                try:
                    time_obj = datetime.strptime(str(time_str).strip(), fmt)
                    return time_obj.hour * 60 + time_obj.minute
                except ValueError:
                    continue
            
            # If all formats fail, try direct conversion of hours
            if isinstance(time_str, (int, float)):
                hours = int(time_str)
                if 0 <= hours <= 24:
                    return hours * 60
            
            self.logger.warning(f"Could not parse time: {time_str}, using default window")
            return 0
        except Exception as e:
            self.logger.error(f"Error converting time {time_str}: {str(e)}")
            return 0
    
    def _prepare_time_windows(self):
        """Prepare time windows for all locations including depot"""
        # Depot time window (assumed to be open all day)
        time_windows = [(0, 24 * 60)]
        
        # Add time windows for all deliveries
        for _, delivery in self.deliveries.iterrows():
            start = self._convert_time_to_minutes(delivery['time_from'])
            end = self._convert_time_to_minutes(delivery['time_to'])
            
            # Ensure end time is after start time
            if end <= start:
                end = max(end, start + 60)  # Add at least 1 hour window
            
            # Ensure reasonable time windows
            start = max(0, min(start, 24 * 60))
            end = max(start + 30, min(end, 24 * 60))
            
            time_windows.append((start, end))
            
        return time_windows
    
    def _log_model_stats(self, manager, routing, solution):
        """Log relevant statistics about the model and solution"""
        self.logger.info(f"Number of locations: {len(self.locations)}")
        self.logger.info(f"Number of vehicles: {self.num_vehicles}")
        
        if not solution:
            self.logger.error("No solution found!")
            # Log time window constraints
            for i, (start, end) in enumerate(self.time_windows):
                if i == 0:
                    self.logger.info(f"Depot window: {start}-{end}")
                else:
                    self.logger.info(f"Location {i} window: {start}-{end}")
            return
        
        self.logger.info("Solution found!")
        total_time = 0
        for vehicle_id in range(self.num_vehicles):
            index = routing.Start(vehicle_id)
            plan_output = f"Route for vehicle {vehicle_id}:\n"
            route_time = 0
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                next_index = solution.Value(routing.NextVar(index))
                route_time += routing.GetArcCostForVehicle(index, next_index, vehicle_id)
                index = next_index
            total_time += route_time
            self.logger.info(plan_output + f'Time of the route: {route_time}min')
        self.logger.info(f'Total time of all routes: {total_time}min')

    def solve(self):
        """Solve the VRP with time windows"""
        # Create routing model
        manager = pywrapcp.RoutingIndexManager(
            len(self.time_matrix),
            self.num_vehicles,
            0  # depot index
        )
        routing = pywrapcp.RoutingModel(manager)
        
        # Register travel time callback
        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return self.time_matrix[from_node][to_node]
        
        transit_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Add time window constraints
        time_dimension_name = 'Time'
        routing.AddDimension(
            transit_callback_index,
            60,  # allow waiting time up to 60 minutes
            24 * 60,  # maximum time per vehicle
            False,  # don't force start cumul to zero
            time_dimension_name
        )
        time_dimension = routing.GetDimensionOrDie(time_dimension_name)
        
        # Add time window constraints for each location
        for location_idx, time_window in enumerate(self.time_windows):
            index = manager.NodeToIndex(location_idx)
            time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])
        
        # Set first solution heuristic
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        
        # Try different strategies if the first one fails
        strategies = [
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION,
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
            routing_enums_pb2.FirstSolutionStrategy.SAVINGS,
            routing_enums_pb2.FirstSolutionStrategy.SWEEP
        ]
        
        for strategy in strategies:
            search_parameters.first_solution_strategy = strategy
            search_parameters.local_search_metaheuristic = (
                routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            )
            search_parameters.time_limit.FromSeconds(30)
            
            # Solve the problem
            solution = routing.SolveWithParameters(search_parameters)
            
            if solution:
                self.logger.info(f"Solution found with strategy: {strategy}")
                break
        
        # Log model statistics
        self._log_model_stats(manager, routing, solution)
        
        if not solution:
            self.logger.error("No solution found with any strategy!")
            return None
        
        # Extract solution
        routes = []
        time_dimension = routing.GetDimensionOrDie('Time')
        
        for vehicle_id in range(self.num_vehicles):
            index = routing.Start(vehicle_id)
            route = []
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                next_index = solution.Value(routing.NextVar(index))
                
                if node_index != 0:  # Skip depot
                    delivery_idx = node_index - 1  # Adjust index for delivery data
                    time_var = time_dimension.CumulVar(index)
                    planned_arrival = solution.Min(time_var)
                    
                    route.append({
                        "package_id": self.deliveries.iloc[delivery_idx]['package_id'],
                        "courier": vehicle_id + 1,
                        "order": len(route) + 1,
                        "route": self.route_name,
                        "planned_arrival": planned_arrival
                    })
                
                index = next_index
            
            if route:  # Only add non-empty routes
                routes.append(route)
        
        return routes

    def validate_input_data(self):
        """Validate input data and log potential issues"""
        try:
            issues = []
            
            # Check if we have enough vehicles
            min_vehicles_needed = len(self.deliveries) // 20 + 1  # Assume max 20 deliveries per vehicle
            if self.num_vehicles < min_vehicles_needed:
                issues.append(f"Warning: May need more vehicles. Have {self.num_vehicles}, recommend at least {min_vehicles_needed}")
            
            # Check for invalid coordinates
            invalid_coords = self.deliveries[
                (self.deliveries['latitude'].isna()) | 
                (self.deliveries['longitude'].isna()) |
                (self.deliveries['latitude'] == 0) | 
                (self.deliveries['longitude'] == 0)
            ]
            if not invalid_coords.empty:
                issues.append(f"Warning: Found {len(invalid_coords)} locations with invalid coordinates")
            
            # Check time windows
            for idx, row in self.deliveries.iterrows():
                start = self._convert_time_to_minutes(row['time_from'])
                end = self._convert_time_to_minutes(row['time_to'])
                if start >= end:
                    issues.append(f"Warning: Invalid time window for delivery {row['package_id']}: {row['time_from']} - {row['time_to']}")
            
            # Log all issues
            for issue in issues:
                self.logger.warning(issue)
                
            return len(issues) == 0
            
        except Exception as e:
            self.logger.error(f"Error validating input data: {str(e)}")
            return False