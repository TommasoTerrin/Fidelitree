import httpx
import asyncio
import os
from app.core.config import settings

SANDBOX_BASE_URL = "https://api.sandbox.digitalhumani.com"
API_KEY = os.getenv("HUMANI_SANDBOX_API_KEY", "bOfSCw2JNb7uVrwPjrm7mIfrzsajTz8y9P7vFlOfG0ZePzLj")
ENTERPRISE_ID = os.getenv("HUMANI_ENTERPRISE_ID", "b3bbe5de")


def _get_headers(api_key: str) -> dict:
    """Prende api key del merchant e la mette nell'header per la chiamata API"""
    if not api_key:
        raise ValueError("API key is required")
    return {"X-Api-Key": api_key}

# Piantare alberi
async def plant_tree(base_url: str, api_key: str, enterprise_id:str, user: str, project_id: str ="44117777", tree_count: int = 1) -> dict:
    payload = {
        "enterpriseId": enterprise_id,
        "projectId": project_id,
        "user": user,
        "treeCount": tree_count,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{base_url}/tree", headers=_get_headers(api_key), json=payload)
        r.raise_for_status() #invia http error se la chiamata fallisce
        return r.json()




# Altri metodi (per ora non utilizzati)
async def get_whoami(base_url: str, api_key: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base_url}/user/whoami", headers=_get_headers(api_key))
        r.raise_for_status()
        return r.json()


async def get_projects(base_url: str, api_key: str) -> list:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base_url}/project", headers=_get_headers(api_key))
        r.raise_for_status()
        return r.json()


####################################################################
# -------------------- Utilities particolari
async def tree_information(base_url: str, tree_id: str, api_key:str):
    async with httpx.AsyncClient() as client:
        # trova albero piantato
        tree_info= await client.get(url= f"{base_url}/tree/{tree_id}", headers=_get_headers(api_key))
        tree_info.raise_for_status()
        tree_info= tree_info.json()

        #Informazioni da passare al frontend quando albero è stato piantato
        project_id = tree_info["projectId"]
        project_info = await client.get(url= f"{base_url}/project/{project_id}", headers=_get_headers(api_key))
        project_info.raise_for_status()
        project_info = project_info.json()
        return tree_info, project_info



async def test_planting_and_info():
    """Funzione di test locale per verificare la corretta creazione di un albero e recupero info."""
    tree= await plant_tree(base_url=SANDBOX_BASE_URL, api_key=API_KEY, enterprise_id=ENTERPRISE_ID, user="test", project_id="44117777", tree_count=1)
    print(tree)
    tree_id= tree["uuid"]
    res= await tree_information(base_url=SANDBOX_BASE_URL, tree_id=tree_id, api_key=API_KEY)
    print(res)

if __name__ == "__main__":
    info= asyncio.run(tree_information(base_url=SANDBOX_BASE_URL, tree_id="11b77ee6-5cab-450b-bdec-22ee3abee04c", api_key=API_KEY))
    print(info)
