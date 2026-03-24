import asyncio
import json
from pipeline.scraper import scrape_url

async def test():
    url = "https://www.space.com/nasa-postpones-artemis-3-moon-landing-2026"
    print(f"Scraping {url}...")
    try:
        result = await scrape_url(url)
        print(f"Text chars: {len(result.get('text', ''))}")
        print(f"Media count: {len(result.get('media', []))}")
        print("\n--- TEXT PREVIEW ---")
        print(result.get('text', '')[:1000])
        print("\n--- SOURCE CAPTURE ---")
        print(json.dumps(result.get('source_capture', {}), indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
