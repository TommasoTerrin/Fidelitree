import asyncio
import httpx
import os

BASE_URL = "http://127.0.0.1:8001"

async def main():
    async with httpx.AsyncClient() as client:
        # create merchant
        resp = await client.post(f"{BASE_URL}/merchant/create")
        print("/merchant/create", resp.status_code, resp.text)
        
        # login
        resp = await client.post(f"{BASE_URL}/merchant/login", data={"password": "prova"})
        print("/merchant/login", resp.status_code, resp.headers.get('location'))
        
        # create a new card
        resp = await client.post(f"{BASE_URL}/get-card")
        print("/get-card", resp.status_code, resp.headers.get('location'))
        
        # follow redirect to view card (ensure leading slash)
        location = resp.headers.get('location')
        if location:
            view_url = f"{BASE_URL}/{location}" if not location.startswith('/') else f"{BASE_URL}{location}"
            resp = await client.get(view_url)
            print("view card", resp.status_code)
            
        # add a point (use same location path)
        if location:
            card_id = location.split('/')[-1]
            # test add-point, which now requires form data for points
            resp = await client.post(f"{BASE_URL}/merchant/add-point/{card_id}", data={"points": 25})
            print("add point (25 pts)", resp.status_code, resp.headers.get('location'))

if __name__ == "__main__":
    asyncio.run(main())
