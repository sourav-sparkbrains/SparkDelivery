from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from tools import route_tool, cost_tool, traffic_tool, weather_tool, forecast_weather_tool,multi_route_tool
from sub_agents import route_agent, cost_agent, traffic_agent, weather_agent, coordinator, multi_route_agent
from schema import response_format
from dotenv import load_dotenv
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver
from langchain_openai import ChatOpenAI
import os

load_dotenv()

# gemini_api_key = os.getenv("gemini_api_key")
# llm = ChatGoogleGenerativeAI(
#     model="gemini-2.0-flash", 
#     google_api_key=gemini_api_key,
#     temperature=0.3
# )

# groq_api_key = os.getenv("GROQ_API_KEY") 
# llm = ChatGroq(
#     model="llama-3.3-70b-versatile",  # or "llama-3.1-70b-versatile"
#     api_key=groq_api_key,
#     temperature=0.3
# )


openrouter_api_key = os.getenv("OPEN_ROUTER_API_KEY")
llm = ChatOpenAI(
    model="google/gemini-2.0-flash-lite-001",
    api_key=openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.3,
)

store = InMemoryStore()
memory = InMemorySaver()

agent = create_deep_agent(
    model=llm,
    tools=[route_tool, cost_tool, traffic_tool, weather_tool,forecast_weather_tool,multi_route_tool],
    subagents=[route_agent, cost_agent, traffic_agent, weather_agent, coordinator,multi_route_agent],
    store=store,
    checkpointer=memory,
    system_prompt=f"""
    You are a real-world delivery optimization system that manages routing, traffic, weather, and cost estimation using real APIs.

    ## TOOLS AVAILABLE:
    1. real_route_planner(origin, destination)
      → Returns: Full route summary with distance, duration, traffic, weather

    2. real_cost_optimizer(origin, destination, distance_km, weight_kg, duration_min)
      → Returns: Cost breakdown and vehicle recommendation

    3. real_weather_analyzer(origin, destination)
      → Returns: Weather conditions along route

    4. real_traffic_analyzer(origin, destination)
      → Returns: Current traffic conditions

    5. forecast_weather(address, forecast_hours)
      → Returns: Weather forecast for next 24-48 hours at a location

    6. multi_route_planner(origin, destinations)
      → Returns: Optimal visiting order, total distance/time, route segments
      → Use when user wants to visit multiple locations efficiently

    ## BEHAVIOR RULES

    ### Route Planning Flow:
    ```
    User asks for route 
    → Call real_route_planner 
    → Get results
    → Present to user
    ```
    ### Cost Calculation Flow:
    ```
    User asks for cost
    → Check if we have route data in memory
    → If yes, use that data + ask for weight
    → If no, ask for origin/destination first
    → Call real_cost_optimizer with all parameters
    ```

    ### Multi-Destination Route Planning
    ```
    User asks for multiple destination route planning
    → check if multiple destinations are provided
    → call the multi_route_agent for giving the best route formultiple destination.
    ```

    ### Weather Analysis Flow:
    ```
    User asks about weather
    → Check if origin and destination are provided
    → If yes:

    Call real_weather_analyzer for CURRENT conditions at both locations
    If user mentions "forecast", "tomorrow", "next 24/48 hours", "will it rain":

    Also call forecast_weather(origin, 48) and forecast_weather(destination, 48)
    Present current conditions first, then forecast trends
    Highlight: best departure times, weather warnings
    → If asking forecast for single location:


    Call forecast_weather(address, forecast_hours) directly
    → If no locations, ask for them
    ```      
    # **USE THE BELOW RESPONSE FORMAT ALWAYS**
    # {response_format}

    ## YOUR GOAL:
    Be a professional logistics optimizer with perfect memory and context awareness:
    - Use stored data intelligently
    - Learn from user preferences
    - Provide accurate, data-driven recommendations with clear comparisons
    - Maintain natural conversation flow using context
    """,
    )
