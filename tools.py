from langchain_core.tools import StructuredTool
from schema import (RouteInput, CostInput, TrafficInput, WeatherInput,ForecastWeatherInput,
                    MultiRouteInput)
from typing import Tuple, Dict
from datetime import datetime,timedelta
from itertools import permutations
from typing import List, Dict
import pickle
import time
import folium
import os
import pandas as pd
import numpy as np
import json

from api import (
    geocode_address_nominatim, get_route_osrm, get_alternative_routes_osrm,
    get_detailed_route_with_instructions, get_realtime_traffic, get_weather_along_route,get_historical_weather
)


def estimate_traffic_from_time() -> float:
    """Estimate traffic based on time of day"""
    current_hour = datetime.now().hour
    
    if 7 <= current_hour <= 10:  
        return 1.5
    elif 17 <= current_hour <= 19: 
        return 1.6
    elif 12 <= current_hour <= 14: 
        return 1.2
    elif 0 <= current_hour <= 5: 
        return 0.8
    else:
        return 1.0

REAL_VEHICLES = [
    {"id": "BIKE-001", "type": "Motorcycle", "capacity_kg": 30, "fuel_cost_per_km": 2.5, "speed_kmph": 40, "available": True},
    {"id": "VAN-001", "type": "Small Van", "capacity_kg": 500, "fuel_cost_per_km": 8.0, "speed_kmph": 50, "available": True},
    {"id": "TRUCK-001", "type": "Light Truck", "capacity_kg": 2000, "fuel_cost_per_km": 15.0, "speed_kmph": 45, "available": True},
    {"id": "TRUCK-002", "type": "Heavy Truck", "capacity_kg": 5000, "fuel_cost_per_km": 25.0, "speed_kmph": 40, "available": True},
]


def calculate_traffic(origin_coords: Tuple[float, float], dest_coords: Tuple[float, float]):
    """Analyze traffic using realtime data"""
    traffic_data = get_realtime_traffic(origin_coords, dest_coords)
    
    if not traffic_data:
        return estimate_traffic_from_time()
    
    try:
        base_time = traffic_data["noTrafficTravelTimeInSeconds"]
        current_time = traffic_data["travelTimeInSeconds"]
        
        if base_time == 0:
            return 1.0 
        
        traffic_factor = current_time / base_time
        traffic_factor = max(0.8, min(traffic_factor, 2.0))
        return round(traffic_factor, 2)
    except KeyError:
        return estimate_traffic_from_time()

def find_optimal_route(origin_coords: Tuple[float, float], 
                       dest_coords: Tuple[float, float]) -> Dict:
    """Compare all available routes and find optimal with detailed instructions"""
    print(f"\n{'='*60}")
    print("Checking for better route")
    print(f"\n{'='*60}")
    
    detailed_routes = get_detailed_route_with_instructions(origin_coords, dest_coords)
    
    if not detailed_routes:
        return None
    
    traffic_factor = calculate_traffic(origin_coords, dest_coords)
    weather_data = get_weather_along_route(origin_coords, dest_coords)
    weather_factor = weather_data.get("weather_factor", 1.0)
    
    scored_routes = []
    for route_data in detailed_routes:
        adjusted_time = route_data['duration_min'] * traffic_factor * weather_factor
        
        fuel_cost_per_km = 8.0
        estimated_cost = route_data['distance_km'] * fuel_cost_per_km
        
        score = (adjusted_time * 0.6) + (estimated_cost * 0.4)
        
        scored_routes.append({
            'route_num': route_data['route_number'],
            'distance_km': route_data['distance_km'],
            'duration_min': route_data['duration_min'],
            'adjusted_duration': adjusted_time,
            'estimated_cost': estimated_cost,
            'score': score,
            'instructions': route_data['instructions'],
            'weather_warnings': weather_data.get('warnings', [])
        })
    
    scored_routes.sort(key=lambda x: x['score'])
    
    return {
        'optimal': scored_routes[0],
        'all_routes': scored_routes,
        'weather_data': weather_data,
        'traffic_factor': traffic_factor
    }

def create_enhanced_map(origin_coords, dest_coords, route_data, weather_data, filename="static/route_map.html", map_type="route"):
    """Generate interactive map with route visualization (supports route/traffic/weather modes)"""
    os.makedirs("static", exist_ok=True)
    
    m = folium.Map(
        location=[(origin_coords[0]+dest_coords[0])/2, (origin_coords[1]+dest_coords[1])/2], 
        zoom_start=8
    )
    
    if map_type == "traffic":
        origin_icon = folium.Icon(color='orange', icon='exclamation-triangle', prefix='fa')
        dest_icon = folium.Icon(color='red', icon='flag-checkered', prefix='fa')
        route_color = '#ff6b6b' 
    elif map_type == "weather":
        origin_icon = folium.Icon(color='blue', icon='cloud', prefix='fa')
        dest_icon = folium.Icon(color='lightblue', icon='cloud-sun', prefix='fa')
        route_color = '#4dabf7'  
    else: 
        origin_icon = folium.Icon(color='green', icon='play')
        dest_icon = folium.Icon(color='red', icon='stop')
        route_color = '#4C763B'  
    
    folium.Marker(
        origin_coords, 
        popup="<b>START</b>", 
        icon=origin_icon
    ).add_to(m)
    
    folium.Marker(
        dest_coords, 
        popup="<b>DESTINATION</b>", 
        icon=dest_icon
    ).add_to(m)
    

    if 'geometry' in route_data and route_data['geometry']:
        coords = [[c[1], c[0]] for c in route_data['geometry']['coordinates']]
        folium.PolyLine(
            coords, 
            color=route_color, 
            weight=5, 
            opacity=0.7,
            tooltip=f"{map_type.title()} Route"
        ).add_to(m)
    
    if map_type == "weather" and weather_data:
        if weather_data.get('origin'):
            origin_w = weather_data['origin']
            folium.CircleMarker(
                origin_coords,
                radius=15,
                popup=f"<b>Origin Weather</b><br>{origin_w.get('temperature')}°C<br>{origin_w.get('description', 'N/A')}",
                color='blue',
                fill=True,
                fillColor='lightblue',
                fillOpacity=0.3
            ).add_to(m)
        
        if weather_data.get('destination'):
            dest_w = weather_data['destination']
            folium.CircleMarker(
                dest_coords,
                radius=15,
                popup=f"<b>Destination Weather</b><br>{dest_w.get('temperature')}°C<br>{dest_w.get('description', 'N/A')}",
                color='blue',
                fill=True,
                fillColor='lightblue',
                fillOpacity=0.3
            ).add_to(m)
        
        if weather_data.get('warnings'):
            mid_lat = (origin_coords[0] + dest_coords[0]) / 2
            mid_lon = (origin_coords[1] + dest_coords[1]) / 2
            folium.Marker(
                [mid_lat, mid_lon],
                popup=f"<b>⚠️ Weather Alert</b><br>{'<br>'.join(weather_data['warnings'])}",
                icon=folium.Icon(color='orange', icon='exclamation-triangle', prefix='fa')
            ).add_to(m)
    
    if map_type == "traffic":
        mid_lat = (origin_coords[0] + dest_coords[0]) / 2
        mid_lon = (origin_coords[1] + dest_coords[1]) / 2
        folium.Marker(
            [mid_lat, mid_lon],
            popup=f"<b>🚦 Traffic Analysis</b><br>Check route details for conditions",
            icon=folium.Icon(color='orange', icon='car', prefix='fa')
        ).add_to(m)
    
    m.save(filename)
    return filename


def create_multi_route_map(origin_coords, best_order, best_routes, filename="static/multi_route_map.html"):
    """Create interactive map for optimal multi-destination route."""
    os.makedirs("static", exist_ok=True)

    all_points = [origin_coords] + [coords for _, coords in best_order]
    avg_lat = sum(p[0] for p in all_points) / len(all_points)
    avg_lon = sum(p[1] for p in all_points) / len(all_points)
    
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=6)

    folium.Marker(
        origin_coords,
        popup=f"<b>START</b><br>{' → '.join([n for n, _ in best_order])}",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)

    for idx, (name, coords) in enumerate(best_order, 1):
        folium.Marker(
            coords,
            popup=f"<b>Stop {idx}</b><br>{name}",
            icon=folium.Icon(color="blue" if idx < len(best_order) else "red", icon="flag")
        ).add_to(m)

    for seg in best_routes:
        if "from" in seg and "to" in seg:
            coords_from = seg["from"]
            to_coords = next((c for n, c in best_order if n == seg["to"]), None)
            if to_coords:
                folium.PolyLine(
                    locations=[[coords_from[0], coords_from[1]], [to_coords[0], to_coords[1]]],
                    color="#4C763B",
                    weight=5,
                    opacity=0.8,
                    tooltip=f"{seg['to']} ({round(seg['duration']/3600,2)}h, {round(seg['distance']/1000,2)} km)"
                ).add_to(m)

    m.save(filename)
    return filename


def real_route_planner(origin: str, destination: str) -> str:
    """Plan route with weather and memory integration"""
    
    print(f"\n{'='*60}")
    print(f"Planning route: {origin} -> {destination}")
    print(f"{'='*60}")
    
    origin_coords = geocode_address_nominatim(origin)
    if not origin_coords:
        return f"Could not find location: {origin}"
    
    dest_coords = geocode_address_nominatim(destination)
    if not dest_coords:
        return f"Could not find location: {destination}"
    
    route = get_route_osrm(origin_coords, dest_coords)
    if not route:
        return f"No route found"
    
    optimization = find_optimal_route(origin_coords, dest_coords)
    if not optimization:
        return f"Could not optimize route"
    
    # Create map filename
    safe_origin = origin.replace(' ', '_').replace(',', '')[:30]
    safe_dest = destination.replace(' ', '_').replace(',', '')[:30]
    map_filename = f"route_{safe_origin}_to_{safe_dest}.html"
    map_path = f"static/{map_filename}"
    
    optimal_route_data = {
        'distance_km': optimization['optimal']['distance_km'],
        'duration_min': optimization['optimal']['adjusted_duration'],
        'instructions': optimization['optimal']['instructions'],
        'geometry': route.get('geometry')
    }
    
    weather_data = optimization.get('weather_data', {})
    
    try:
        create_enhanced_map(origin_coords, dest_coords, optimal_route_data, weather_data, map_path,map_type="route")
        map_url = f"/view-map/{map_filename}"
    except Exception as e:
        print("Map creation failed:", e)
        map_url = None
    
    result = f"ROUTE SUMMARY\n"
    result += f"Origin: {origin}\n"
    result += f"Destination: {destination}\n"
    result += f"Distance: {route['distance_km']:.1f} km\n"
    result += f"Base Duration: {route['duration_min']:.0f} min\n"
    result += f"Adjusted ETA: {optimization['optimal']['adjusted_duration']:.0f} min\n\n"
    
    if map_url:
        result += f"INTERACTIVE MAP: {map_url}\n\n"
    
    result += f"TRAFFIC ANALYSIS\n"
    traffic_factor = optimization.get('traffic_factor', 1.0)
    if traffic_factor >= 1.5:
        traffic_level = "Heavy"
        advice = "Consider delaying by 1-2 hours or use alternative route"
    elif traffic_factor >= 1.2:
        traffic_level = "Moderate"
        advice = "Expect minor delays, monitor conditions"
    else:
        traffic_level = "Light"
        advice = "Good time to depart"
    
    result += f"Current Traffic: {traffic_level}\n"
    result += f"Traffic Factor: {traffic_factor:.2f}x\n"
    
    base_duration = route['duration_min']
    adjusted = optimization['optimal']['adjusted_duration']
    delay = adjusted - base_duration
    result += f"Expected Delay: {delay:.0f} min\n"
    result += f"Advice: {advice}\n\n"
    
    result += f"WEATHER CONDITIONS\n"
    origin_w = weather_data.get('origin', {})
    dest_w = weather_data.get('destination', {})
    if origin_w:
        result += f"Origin: {origin_w.get('temperature', 'N/A')}°C, {origin_w.get('condition', 'N/A')}\n"
    if dest_w:
        result += f"Destination: {dest_w.get('temperature', 'N/A')}°C, {dest_w.get('condition', 'N/A')}\n"
    
    if optimization['optimal'].get('weather_warnings'):
        result += f"\nWeather Alerts:\n"
        for warning in optimization['optimal']['weather_warnings']:
            result += f"  • {warning}\n"

    return result 

def multi_route_planner(origin: str, destinations: List[str]) -> str:
    """Plan optimal multi-destination route minimizing total travel time."""
    print(f"\n{'='*60}")
    print(f"Planning routes from {origin} to destinations...")
    
    origin_coords = geocode_address_nominatim(origin)
    if not origin_coords:
        return f"Could not find location: {origin}"
    
    print(f"Origin coordinates: {origin_coords}")
    
    dest_coords = []
    for dest in destinations:
        print(f"  - {dest}")
        coords = geocode_address_nominatim(dest)
        if coords:
            dest_coords.append((dest, coords))
            print(f"    Coordinates: {coords}")
        else:
            print(f"    ⚠️  Could not find location: {dest}")
    
    if not dest_coords:
        return "No valid destination coordinates found."
    
    print(f"\n{'='*60}")
    print(f"Testing route connectivity...")
    print(f"{'='*60}")
    
    for dest_name, dest_coord in dest_coords:
        route = get_route_osrm(origin_coords, dest_coord)
        print(f"\nRoute from {origin} to {dest_name}:")
        if route:
            # Check both formats
            duration = route.get('duration', route.get('duration_min', 0))
            distance = route.get('distance', route.get('distance_km', 0))
            print(f"  ✓ Duration: {duration} {'seconds' if 'duration' in route else 'minutes'}")
            print(f"  ✓ Distance: {distance} {'meters' if 'distance' in route else 'km'}")
            print(f"  ✓ Full response keys: {route.keys()}")
        else:
            print(f"  ✗ Route returned None or empty")
    
    best_order = None
    best_time = float("inf")
    best_routes = []
    tested_permutations = 0

    print(f"\n{'='*60}")
    print(f"Testing all route permutations...")
    print(f"{'='*60}")

    for order in permutations(dest_coords):
        tested_permutations += 1
        total_time = 0
        total_distance = 0
        current_point = origin_coords
        valid_route = True
        route_segments = []

        for dest_name, dest_coord in order:
            route = get_route_osrm(current_point, dest_coord)
            
            if route and isinstance(route, dict):
                duration = route.get("duration", 0)
                distance = route.get("distance", 0)
                
                if duration == 0 and "duration_min" in route:
                    duration = route.get("duration_min", 0) * 60  
                if distance == 0 and "distance_km" in route:
                    distance = route.get("distance_km", 0) * 1000 
                
                if duration > 0:  
                    total_time += duration
                    total_distance += distance
                    route_segments.append({
                        "from": current_point,
                        "to": dest_name,
                        "duration": duration,
                        "distance": distance
                    })
                    current_point = dest_coord
                else:
                    valid_route = False
                    break
            else:
                valid_route = False
                break

        if valid_route and total_time < best_time:
            best_time = total_time
            best_order = order
            best_routes = route_segments
            print(f"  ✓ Found valid route #{tested_permutations} | Time: {round(total_time/3600, 2)}h")

    print(f"\nTotal permutations tested: {tested_permutations}")

    if not best_order:
        return f"❌ No valid routes found for any combination after testing {tested_permutations} permutations.\n\nPossible issues:\n- OSRM service may be unavailable\n- Route data missing 'duration' field\n- Network connectivity issues"

    result = f"\n{'='*60}\n"
    result += f"OPTIMAL MULTI-ROUTE PLAN\n{'='*60}\n"
    result += f"Starting from: {origin}\n\n"
    
    result += "Best visiting order:\n"
    for i, (name, _) in enumerate(best_order, 1):
        result += f"  {i}. {name}\n"
    
    result += f"\nTotal Travel Time: {round(best_time/3600, 2)} hours\n"
    total_dist_km = round(sum(r['distance'] for r in best_routes) / 1000, 2)
    result += f"Total Distance: {total_dist_km} km\n\n"

    result += "Route Details:\n"
    prev_loc = origin
    for r in best_routes:
        result += f"  {prev_loc} → {r['to']}\n"
        result += f"    Time: {round(r['duration']/3600, 2)}h | Distance: {round(r['distance']/1000, 2)} km\n"
        prev_loc = r['to']

    try:
        safe_origin = origin.replace(' ', '_').replace(',', '')[:30]
        map_filename = f"multi_route_from_{safe_origin}.html"
        map_path = f"static/{map_filename}"
        create_multi_route_map(origin_coords, best_order, best_routes, map_path)
        map_url = f"/view-map/{map_filename}"
        print(f"✓ Multi-route map created: {map_path}") 
        print(f"✓ Map URL: {map_url}")
    except Exception as e:
        print("Map creation failed:", e)
        map_url = None

    result += f"\n{'='*60}\n"
    if map_url:
        result += f"INTERACTIVE MAP: {map_url}\n"
    else:
        result += "Map generation failed.\n"

    return result



def real_cost_optimizer(origin: str, destination: str, distance_km: float, weight_kg: float, duration_min: float) -> str:
    """Calculate costs with weather impact"""
    origin_coords = geocode_address_nominatim(origin)
    dest_coords = geocode_address_nominatim(destination)
    
    print(f"\n{'='*60}")
    print("Inside the cost optimizer")
    print(f"\n{'='*60}")

    suitable = [v for v in REAL_VEHICLES if v["capacity_kg"] >= weight_kg and v["available"]]
    
    if not suitable:
        return f"No vehicle available for {weight_kg}kg"
    
    traffic_multiplier = calculate_traffic(origin_coords, dest_coords)
    weather_data = get_weather_along_route(origin_coords, dest_coords)
    weather_multiplier = weather_data.get("weather_factor", 1.0)
    
    options = []
    for vehicle in suitable:
        fuel_cost = distance_km * vehicle["fuel_cost_per_km"]
        driver_cost = (duration_min / 60) * 200
        base_fee = 150
        
        capacity_usage = weight_kg / vehicle["capacity_kg"]
        capacity_multiplier = 1.15 if capacity_usage > 0.8 else 1.0
        
        total_cost = (base_fee + fuel_cost + driver_cost) * traffic_multiplier * weather_multiplier * capacity_multiplier
        
        options.append({
            "vehicle": vehicle,
            "total_cost": total_cost,
            "fuel_cost": fuel_cost,
            "driver_cost": driver_cost,
            "traffic_factor": traffic_multiplier,
            "weather_factor": weather_multiplier
        })
    
    options.sort(key=lambda x: x["total_cost"])
    best = options[0]
    
    result = f"\nCOST ESTIMATE\n"
    result += f"Recommended Vehicle: {best['vehicle']['type']} ({best['vehicle']['id']})\n"
    result += f"Total Cost: Rs {best['total_cost']:.2f}\n\n"
    result += f"Cost Breakdown:\n"
    result += f"  • Base Fee: Rs 150\n"
    result += f"  • Fuel Cost: Rs {best['fuel_cost']:.2f}\n"
    result += f"  • Driver Cost: Rs {best['driver_cost']:.2f}\n"
    result += f"  • Traffic Multiplier: {best['traffic_factor']:.2f}x\n"
    result += f"  • Weather Multiplier: {best['weather_factor']:.2f}x\n"
    
    return result

def real_weather_analyzer(origin: str, destination: str) -> str:
    """Analyze weather conditions along route"""

    print(f"\n{'='*60}")
    print("Inside the weather analyzer")
    print(f"\n{'='*60}")

    origin_coords = geocode_address_nominatim(origin)
    dest_coords = geocode_address_nominatim(destination)
    
    if not origin_coords or not dest_coords:
        return "Could not analyze weather - invalid locations"
    
    weather_data = get_weather_along_route(origin_coords, dest_coords)
    
    result = f"WEATHER ANALYSIS\n\n"
    
    if weather_data.get('origin'):
        origin_weather = weather_data['origin']
        result += f"Origin Weather:\n"
        result += f"  Temperature: {origin_weather.get('temperature', 'N/A')}°C (feels like {origin_weather.get('feels_like', 'N/A')}°C)\n"
        result += f"  Condition: {origin_weather.get('description', 'N/A').title()}\n"
        result += f"  Humidity: {origin_weather.get('humidity', 'N/A')}%\n"
        result += f"  Wind Speed: {origin_weather.get('wind_speed', 'N/A')} m/s\n"
        if origin_weather.get('rain', 0) > 0:
            result += f"  Rain: {origin_weather['rain']:.1f} mm/h\n"
        result += "\n"
    
    if weather_data.get('destination'):
        dest_weather = weather_data['destination']
        result += f"Destination Weather:\n"
        result += f"  Temperature: {dest_weather.get('temperature', 'N/A')}°C\n"
        result += f"  Condition: {dest_weather.get('description', 'N/A').title()}\n\n"
    
    if weather_data.get('warnings'):
        result += f"Weather Alerts:\n"
        for warning in weather_data['warnings']:
            result += f"  • {warning}\n"
        result += f"\nWeather Impact Factor: {weather_data.get('weather_factor', 1.0):.2f}x\n"
        result += f"Recommendation: Exercise caution. Delivery time may increase by {(weather_data.get('weather_factor', 1.0) - 1) * 100:.0f}%\n"
    else:
        result += f"Good weather conditions for delivery.\n"
    
    safe_origin = origin.replace(' ', '_').replace(',', '')[:30]
    safe_dest = destination.replace(' ', '_').replace(',', '')[:30]
    map_filename = f"weather_{safe_origin}_to_{safe_dest}.html"
    map_path = f"static/{map_filename}"

    route = get_route_osrm(origin_coords, dest_coords)
    if route:
        route_data = {
            'geometry': route.get('geometry')
        }
        create_enhanced_map(origin_coords, dest_coords, route_data, weather_data, map_path, map_type="weather")

    result += f"\nINTERACTIVE MAP: /view-map/{map_filename}\n"

    return result

def real_traffic_analyzer(origin: str, destination: str) -> str:
    """Analyze traffic conditions using real data and patterns"""
    print(f"\nAnalyzing traffic: {origin} -> {destination}")
    
    origin_coords = geocode_address_nominatim(origin)
    dest_coords = geocode_address_nominatim(destination)
    
    if not origin_coords or not dest_coords:
        return "Could not analyze traffic - invalid locations"
    
    route = get_route_osrm(origin_coords, dest_coords)
    if not route:
        return "No route found for traffic analysis"
    
    current_hour = datetime.now().hour
    traffic_factor = calculate_traffic(origin_coords, dest_coords)
    
    if traffic_factor >= 1.5:
        traffic_level = "Heavy"
        advice = "Consider delaying by 1-2 hours or use alternative route"
    elif traffic_factor >= 1.2:
        traffic_level = "Moderate"
        advice = "Expect minor delays, monitor conditions"
    else:
        traffic_level = "Light"
        advice = "Good time to depart"
    
    base_duration = route["duration_min"]
    adjusted_duration = base_duration * traffic_factor
    total_delay = adjusted_duration - base_duration
    
    result = (
        f"TRAFFIC ANALYSIS\n"
        f"Current Traffic: {traffic_level}\n"
        f"Time: {datetime.now().strftime('%H:%M')} (Factor: {traffic_factor:.2f}x)\n"
        f"Base ETA: {base_duration:.0f} min\n"
        f"Adjusted ETA: {adjusted_duration:.0f} min\n"
        f"Expected Delay: {total_delay:.0f} min\n\n"
        f"Advice: {advice}\n"
    )
 
    safe_origin = origin.replace(' ', '_').replace(',', '')[:30]
    safe_dest = destination.replace(' ', '_').replace(',', '')[:30]
    map_filename = f"traffic_{safe_origin}_to_{safe_dest}.html"
    map_path = f"static/{map_filename}"

    if route:
        route_data = {
            'geometry': route.get('geometry')
        }
        create_enhanced_map(origin_coords, dest_coords, route_data, {}, map_path, map_type="traffic")

    result += f"\nINTERACTIVE MAP: /view-map/{map_filename}\n"

    return result


def forecast_weather(address, forecast_hours=48):
    """Generate 48-hour weather forecast for a given address using trained VAR model"""

    model_path = "models/weather_var_model.pkl"
    meta_path = "models/model_meta.json"
    
    with open(model_path, "rb") as f:
        results = pickle.load(f)

    with open(meta_path, "r") as f:
        meta = json.load(f)

    non_stationary_cols = meta["non_stationary_cols"]
    main_vars = meta["main_vars"]

    lat, lon = geocode_address_nominatim(address)

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=15)

    df = get_historical_weather(lat, lon, start_date=start_date.strftime("%Y-%m-%d"), end_date=end_date.strftime("%Y-%m-%d"))
    if df is None or df.empty:
        raise ValueError("No historical weather data available for this location.")

    df.set_index('time', inplace=True)

    df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)
    df['day_sin'] = np.sin(2 * np.pi * df.index.dayofyear / 365)
    df['day_cos'] = np.cos(2 * np.pi * df.index.dayofyear / 365)


    df_main = df[main_vars].copy()

    df_trans = df_main.copy()
    for col in non_stationary_cols:
        df_trans[col] = df_trans[col].diff()
    df_trans = df_trans.dropna()

    lag_order = results.k_ar
    if len(df_trans) < lag_order:
        raise ValueError(f"Insufficient data ({len(df_trans)} rows) for lag order {lag_order}")

    input_data = df_trans.values[-lag_order:]

    forecast = results.forecast(input_data, steps=forecast_hours)
    forecast_df = pd.DataFrame(forecast, columns=df_trans.columns)

    forecast_final = forecast_df.copy()
    for col in df_trans.columns:
        if col in non_stationary_cols:
            last_val = df_main[col].iloc[-1]
            forecast_final[col] = forecast_df[col].cumsum() + last_val
        else:
            forecast_final[col] = forecast_df[col]


    last_time = df.index[-1]
    future_index = pd.date_range(start=last_time + pd.Timedelta(hours=1),
                                 periods=forecast_hours, freq='h')
    forecast_final.index = future_index

    result = f"WEATHER FORECAST for {address}\n"
    result += f"Forecast Period: Next {forecast_hours} hours\n\n"
    
    for i in range(0, min(forecast_hours, 48), 6):
        time_str = future_index[i].strftime('%Y-%m-%d %H:%M')
        result += f"\n{time_str}:\n"
        for col in forecast_final.columns:
            if col in ['temperature', 'humidity', 'rain', 'wind_speed']:
                result += f"  {col}: {forecast_final[col].iloc[i]:.2f}\n"
    
    return result




route_tool = StructuredTool.from_function(
    func=real_route_planner,
    name="real_route_planner",
    description="Plan route with weather and traffic integration. Returns distance and duration from API.",
    args_schema=RouteInput
)

multi_route_tool = StructuredTool.from_function(
    func=multi_route_planner,
    name="multi_route_planner",
    description="Plan optimal multi-destination route. Finds best visiting order to minimize total travel time. Use when user wants to visit multiple locations.",
    args_schema=MultiRouteInput
)

cost_tool = StructuredTool.from_function(
    func=real_cost_optimizer,
    name="real_cost_optimizer",
    description="Calculate delivery costs with weather and traffic factors. ONLY use when user provides weight.",
    args_schema=CostInput
)

traffic_tool = StructuredTool.from_function(
    func=real_traffic_analyzer,
    name="real_traffic_analyzer",
    description="Analyze traffic conditions using real patterns",
    args_schema=TrafficInput
)

weather_tool = StructuredTool.from_function(
    func=real_weather_analyzer,
    name="real_weather_analyzer",
    description="Analyze weather conditions along route",
    args_schema=WeatherInput
)

forecast_weather_tool = StructuredTool.from_function(
    func=forecast_weather,
    name="forecast_weather", 
    description="Forecast weather conditions for the next 48 hours at a location",
    args_schema=ForecastWeatherInput
)
