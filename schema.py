from pydantic import BaseModel, Field
from typing import List, Optional

#-------------------------Input Format-----------------------------

class RouteInput(BaseModel):
    origin: str = Field(description="Starting location")
    destination: str = Field(description="Ending location")

class MultiRouteInput(BaseModel):
    origin: str = Field(description="Starting location")
    destinations: List[str] = Field(description="List of destination locations to visit")

class CostInput(BaseModel):
    origin: str
    destination: str
    distance_km: float
    weight_kg: float
    duration_min: float

class TrafficInput(BaseModel):
    origin: str
    destination: str

class WeatherInput(BaseModel):
    origin: str
    destination: str

class ForecastWeatherInput(BaseModel):
    address: str
    forecast_hours: int = Field(default=48, description="Number of hours to forecast (default: 48)")



response_format = """
    # ## RESPONSE FORMATS

    **For Route-Only Queries:** 
    ROUTE SUMMARY Origin: [origin] 
    Destination: [destination] 
    Distance: [X] km 
    Base Duration: [Y] min 
    Adjusted ETA: [Z] min (includes traffic and weather) 

    TRAFFIC ANALYSIS 
    Current Traffic: [level] 
    Traffic Factor: [X]x 
    Expected Delay: [Y] min 
    Advice: [recommendation] 

    WEATHER CONDITIONS 
    Origin: [temp]°C, [condition] 
    Destination: [temp]°C, [condition] 
    Warnings: [if any] 

    **For Full Planning (Route + Cost):
    ** ROUTE SUMMARY 
    ... 
    COST ESTIMATE 
    Recommended Vehicle: [type] ([ID]) 
    Total Cost: Rs [amount] 
    Cost Breakdown: 
    • Base Fee: Rs 150 
    • Fuel Cost: Rs [X] 
    • Driver Cost: Rs [Y] 
    • Traffic Multiplier: [X]x 
    • Weather Multiplier: [X]x

    **For Multi-Destination Route Planning:**
    ```
    OPTIMAL MULTI-ROUTE PLAN
    Starting from: [origin]

    Best visiting order:
      1. [destination 1]
      2. [destination 2]
      3. [destination 3]
      ...

    Total Travel Time: [X] hours
    Total Distance: [Y] km

    Route Details:
      [origin] → [destination 1]
        Time: [X]h | Distance: [Y] km
      [destination 1] → [destination 2]
        Time: [X]h | Distance: [Y] km
      [destination 2] → [destination 3]
        Time: [X]h | Distance: [Y] km

    OPTIMIZATION SUMMARY:
      • Route optimized to minimize total travel time
      • Tested all possible visiting orders
      • This sequence saves approximately [X] minutes compared to worst route
      
    RECOMMENDATIONS:
      • Estimated total journey: [X] hours
      • Consider [traffic/weather advice if available]
      • Plan for fuel stops every [X] km
    ```

    **For Weather Analysis (Current Only):**
    ```
    WEATHER ANALYSIS

    Origin Weather ([location]):
      Temperature: [X]°C (feels like [Y]°C)
      Condition: [description]
      Humidity: [X]%
      Wind Speed: [X] m/s
      Rain: [X] mm/h (if applicable)

    Destination Weather ([location]):
      Temperature: [X]°C
      Condition: [description]

    Weather Alerts: (if any)
      • [warning 1]
      • [warning 2]

    Weather Impact Factor: [X]x
    Recommendation: [advice based on conditions]

    **For Weather Analysis (Current + Forecast):**
    WEATHER ANALYSIS

    CURRENT CONDITIONS
    Origin: [temp]°C, [condition]
    Destination: [temp]°C, [condition]

    WEATHER FORECAST (Next 24-48 Hours)
    Origin ([location]):
      [Time]: Temp: [X]°C, Rain: [Y]mm
      [Time]: Temp: [X]°C, Rain: [Y]mm

    Destination ([location]):
      [Time]: Temp: [X]°C, Rain: [Y]mm
      [Time]: Temp: [X]°C, Rain: [Y]mm

    RECOMMENDATIONS:
      • Best departure time: [time]
      • Travel advice: [recommendations]

    **For Forecast-Only Queries:**
    WEATHER FORECAST for [location]
    Forecast Period: Next [X] hours

    [Time 1]: Temp: [X]°C, Humidity: [Y]%, Rain: [Z]mm
    [Time 2]: Temp: [X]°C, Humidity: [Y]%, Rain: [Z]mm

    SUMMARY:
      • Best travel window: [time range]
      • Rain expected: [Yes/No]
    ```
    **For Route Improvements (with comparison):**
    ```
    ROUTE SUMMARY
    Origin: [origin]
    Destination: [destination]
    Distance: [distance_km] km
    Duration: [duration_min] min

    {% if new_duration < old_duration %}
    ✓ IMPROVEMENT DETECTED:
    This route saves approximately [old_duration - new_duration] minutes 
    compared to your previous one ([old_duration] min → [new_duration] min).

    TRAFFIC: [traffic_level] - [advice]
    WEATHER: [weather_conditions]

    {% else %}
    No faster alternative was found — your current route remains optimal 
    ([old_duration] min). Traffic and weather conditions don’t justify a change.

    TRAFFIC: [traffic_level] - [advice]
    WEATHER: [weather_conditions]

    {% endif %}

    ```
"""