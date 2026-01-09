import requests
import time
import os
import pandas as pd
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv


load_dotenv()

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")



def get_historical_weather(lat: float, lon: float, start_date: str, end_date: str):
    """Fetch hourly historical weather directly from Open-Meteo API (no SDK)."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": "temperature_2m,relative_humidity_2m,rain,snowfall,wind_speed_10m",
        "timezone": "auto"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        hourly = data.get("hourly", {})
        df = pd.DataFrame({
            "time": hourly.get("time", []),
            "temperature": hourly.get("temperature_2m", []),
            "humidity": hourly.get("relative_humidity_2m", []),
            "rain": hourly.get("rain", []),
            "snow": hourly.get("snowfall", []),
            "wind_speed": hourly.get("wind_speed_10m", []),
        })

        df["time"] = pd.to_datetime(df["time"])
        return df

    except Exception as e:
        print(f"Historical weather error: {e}")
        return None


def get_realtime_traffic(origin_coords: Tuple[float, float], dest_coords: Tuple[float, float]) -> Optional[Dict]:
    """Get real-time traffic using TomTom API"""
    base_url = "https://api.tomtom.com/routing/1/calculateRoute"
    origin = f"{origin_coords[0]},{origin_coords[1]}"
    destination = f"{dest_coords[0]},{dest_coords[1]}"
    url = f"{base_url}/{origin}:{destination}/json"
    
    headers = {"Accept": "application/json"}
    params = {
        "key": TOMTOM_API_KEY,
        "traffic": "true",
        "computeTravelTimeFor": "all",
        "routeType": "fastest",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data["routes"][0]["summary"]
    except Exception as e:
        print(f"Error fetching traffic data: {e}")
        return None


def get_weather_data(lat: float, lon: float) -> Optional[Dict]:
    """
    Get weather data using OpenWeatherMap API
    Returns: temperature, condition, precipitation, wind speed
    """
    if not OPENWEATHER_API_KEY:
        return None
    
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return {
            "temperature": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "condition": data["weather"][0]["main"],
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data["wind"]["speed"],
            "rain": data.get("rain", {}).get("1h", 0),
            "visibility": data.get("visibility", 10000) / 1000  # km
        }
    except Exception as e:
        print(f"Weather API error: {e}")
        return None


def get_weather_along_route(origin_coords: Tuple[float, float], 
                            dest_coords: Tuple[float, float]) -> Dict:
    """
    Get weather for origin and destination, calculate weather impact
    """
    origin_weather = get_weather_data(origin_coords[0], origin_coords[1])
    dest_weather = get_weather_data(dest_coords[0], dest_coords[1])
    
    weather_factor = 1.0
    warnings = []
    
    if origin_weather:
        if origin_weather["rain"] > 2.5:
            weather_factor += 0.3
            warnings.append(f"Heavy rain at origin ({origin_weather['rain']:.1f}mm/h)")
        elif origin_weather["rain"] > 0.5:
            weather_factor += 0.15
            warnings.append(f"Light rain at origin ({origin_weather['rain']:.1f}mm/h)")
        
        # Visibility impact
        if origin_weather["visibility"] < 1:
            weather_factor += 0.2
            warnings.append(f"Low visibility at origin ({origin_weather['visibility']:.1f}km)")
        
        # Wind impact
        if origin_weather["wind_speed"] > 15:
            weather_factor += 0.1
            warnings.append(f"Strong winds at origin ({origin_weather['wind_speed']:.1f}m/s)")
    
    if dest_weather:
        if dest_weather["rain"] > 2.5:
            weather_factor += 0.2
            warnings.append(f"Heavy rain at destination ({dest_weather['rain']:.1f}mm/h)")
        elif dest_weather["rain"] > 0.5:
            weather_factor += 0.1
    
    return {
        "origin": origin_weather,
        "destination": dest_weather,
        "weather_factor": min(weather_factor, 1.8),
        "warnings": warnings
    }


def geocode_address_nominatim(address: str) -> Optional[Tuple[float, float]]:
    """Geocoding using Nominatim (OpenStreetMap)"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "DeliveryOptimizationSystem/1.0" 
    }
    
    try:
        time.sleep(1)  
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data:
            return (float(data[0]["lat"]), float(data[0]["lon"]))
        return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None


def get_route_osrm(origin_coords: Tuple[float, float], 
                   dest_coords: Tuple[float, float]) -> Optional[Dict]:
    """Routing using OSRM (OpenStreetMap Routing Machine)"""
    lat1, lon1 = origin_coords
    lat2, lon2 = dest_coords
    
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "annotations": "true"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return {
                "distance_km": route["distance"] / 1000,
                "duration_min": route["duration"] / 60,
                "geometry": route["geometry"],
                "steps": route["legs"][0].get("steps", [])
            }
        return None
    except Exception as e:
        print(f"Routing error: {e}")
        return None


def get_alternative_routes_osrm(origin_coords: Tuple[float, float], 
                                dest_coords: Tuple[float, float]) -> list:
    """Get multiple route options"""
    lat1, lon1 = origin_coords
    lat2, lon2 = dest_coords
    
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {
        "alternatives": "true", 
        "steps": "true",
        "overview": "full"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if data.get("code") == "Ok":
            routes = []
            for route in data.get("routes", []):
                routes.append({
                    "distance_km": route["distance"] / 1000,
                    "duration_min": route["duration"] / 60
                })
            return routes
        return []
    except:
        return []


def get_detailed_route_with_instructions(origin_coords: Tuple[float, float], 
                                         dest_coords: Tuple[float, float]) -> Optional[Dict]:
    """Get detailed route with turn-by-turn instructions and road names"""
    lat1, lon1 = origin_coords
    lat2, lon2 = dest_coords
    
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    params = {
        "alternatives": "true",
        "steps": "true",
        "overview": "full",
        "geometries": "geojson",
        "annotations": "true"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") == "Ok" and data.get("routes"):
            all_routes = []
            
            for route_idx, route in enumerate(data.get("routes", [])):
                route_info = {
                    "route_number": route_idx + 1,
                    "distance_km": route["distance"] / 1000,
                    "duration_min": route["duration"] / 60,
                    "instructions": []
                }
                
                for leg in route.get("legs", []):
                    for step in leg.get("steps", []):
                        instruction = {
                            "distance_km": step["distance"] / 1000,
                            "duration_min": step["duration"] / 60,
                            "instruction": step.get("maneuver", {}).get("type", "continue"),
                            "road_name": step.get("name", "Unnamed road"),
                            "direction": step.get("maneuver", {}).get("modifier", "")
                        }
                        route_info["instructions"].append(instruction)
                
                all_routes.append(route_info)
            
            return all_routes
        return None
    except Exception as e:
        print(f"Detailed routing error: {e}")
        return None

