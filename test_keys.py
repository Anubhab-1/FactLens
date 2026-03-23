import os
import asyncio
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_community.tools.tavily_search import TavilySearchResults

load_dotenv("factlens/backend/.env")

async def test_keys():
    print("Testing Tavily API Key...")
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print("❌ TAVILY_API_KEY not found in .env")
    else:
        try:
            search = TavilySearchResults(tavily_api_key=tavily_key)
            results = search.run("What is the capital of France?")
            print(f"✅ Tavily working. Results found: {len(results)}")
        except Exception as e:
            print(f"❌ Tavily failed: {e}")

    print("\nTesting NVIDIA API Key...")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if not nvidia_key:
        print("❌ NVIDIA_API_KEY not found in .env")
    else:
        try:
            llm = ChatNVIDIA(model="meta/llama-3.1-8b-instruct", api_key=nvidia_key)
            response = llm.invoke("Hello, are you working?")
            print(f"✅ NVIDIA working. Response: {response.content[:50]}...")
        except Exception as e:
            print(f"❌ NVIDIA failed: {e}")

    print("\nTesting Google Gemini API Key...")
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not google_key:
        print("❌ GOOGLE_API_KEY / GEMINI_API_KEY not found in .env")
    else:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", google_api_key=google_key)
            response = llm.invoke("Hello, are you working?")
            print(f"✅ Google Gemini working. Response: {response.content[:50]}...")
        except Exception as e:
            print(f"❌ Google Gemini failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_keys())
