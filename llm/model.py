import os
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv

load_dotenv()


groq_api_key = os.getenv("GROQ_API_KEY")
groq_llm = ChatGroq(
    model="moonshotai/kimi-k2-instruct-0905",
    # "llama-3.3-70b-versatile",
    api_key=groq_api_key,
    temperature=0.3
)


openrouter_api_key = os.getenv("OPEN_ROUTER_API_KEY")
gemeni_llm = ChatOpenAI(
    model="google/gemini-2.0-flash-lite-001",
    api_key=openrouter_api_key,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.3,
)

