import os
import httpx
from dotenv import load_dotenv

# Carica le variabili dal file .env
load_dotenv()

API_KEY = os.getenv("HUMANI_SANDBOX_API_KEY")
ENTERPRISE_ID = os.getenv("HUMANI_ENTERPRISE_ID")
BASE_URL = "https://api.sandbox.digitalhumani.com"

headers = {
    "X-Api-Key": API_KEY,
    "Content-Type": "application/json"
}

def test_whoami():
    print("--- Testing /user/whoami ---")
    url = f"{BASE_URL}/user/whoami"
    with httpx.Client() as client:
        # Simplificando gli headers per vedere se cambia qualcosa
        test_headers = {"X-Api-Key": API_KEY}
        response = client.get(url, headers=test_headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Success! Authenticated as:")
            print(response.json())
        else:
            print("Error: Unauthorized. Check if your API Key is valid for the Sandbox environment.")
            print(f"Response Body: {response.text}")
    print()

def test_enterprise():
    print(f"--- Testing /enterprise/{ENTERPRISE_ID} ---")
    url = f"{BASE_URL}/enterprise/{ENTERPRISE_ID}"
    with httpx.Client(headers=headers) as client:
        response = client.get(url)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Response:", response.json())
        else:
            print("Error:", response.text)
    print()

def test_projects():
    print("--- Testing /project ---")
    url = f"{BASE_URL}/project"
    with httpx.Client(headers=headers) as client:
        response = client.get(url)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            projects = response.json()
            print(f"Number of projects found: {len(projects)}")
            if projects:
                print("First project example:", projects[0])
        else:
            print("Error:", response.text)
    print()

if __name__ == "__main__":
    if not API_KEY or not ENTERPRISE_ID:
        print("Error: HUMANI_API_KEY and HUMANI_ENTERPRISE_ID must be set in .env file")
    else:
        test_whoami()
        test_enterprise()
        test_projects()
