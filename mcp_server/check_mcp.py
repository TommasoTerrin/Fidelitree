import asyncio
import httpx

async def check_routes():
    url = "http://localhost:8000/mcp/sse"
    print(f"Checking {url}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_routes())
