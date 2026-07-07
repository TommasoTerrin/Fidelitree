import httpx
import asyncio
from app.core.config import settings


def _get_headers(api_key: str) -> dict:
    """Restituisce gli header di autenticazione per l'API Ecologi (Bearer Token)."""
    if not api_key:
        raise ValueError("API key is required")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# Acquistare alberi
async def purchase_trees(
    number: int = 1,
    name: str | None = None,
    test: bool = True,
    sandbox: bool = True,
) -> dict:
    """
    Acquista alberi tramite l'API Ecologi.

    POST /impact/trees

    Args:
        number: Numero di alberi da acquistare (required).
        name: Etichetta per l'acquisto, es. nome cliente o ID ordine (optional).
              Sarà visibile sul profilo Ecologi. Attenzione ai dati personali (PII).
        test: Se True, la chiamata non addebita nulla e non aggiunge alberi al profilo.
        sandbox: Se True usa l'URL sandbox e la chiave sandbox, altrimenti produzione.
    
    Returns:
        dict con la risposta dell'API Ecologi.
    """
    if sandbox:
        base_url = settings.ECOLOGI_SANDBOX_URL
        api_key = settings.ECOLOGI_SANDBOX_API_KEY
    else:
        base_url = settings.ECOLOGI_URL
        api_key = settings.ECOLOGI_API_KEY

    payload: dict = {"number": number}

    if name is not None:
        payload["name"] = name

    if test:
        payload["test"] = True

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base_url}/impact/trees",
            headers=_get_headers(api_key),
            json=payload,
        )
        r.raise_for_status()  # invia http error se la chiamata fallisce
        return r.json()


####################################################################
# -------------------- Test standalone
async def test_purchase():
    """
    Funzione di test standalone per verificare la chiamata all'API Ecologi.
    Usa sandbox + flag test=True, quindi non addebita nulla.
    """
    print("--- Test Ecologi: Purchase Trees (sandbox + test=True) ---")
    print(f"Sandbox URL: {settings.ECOLOGI_SANDBOX_URL}")
    print(f"Sandbox API Key presente: {'Sì' if settings.ECOLOGI_SANDBOX_API_KEY else 'No'}")

    try:
        result = await purchase_trees(
            number=1,
            name="fidelitree-test",
            test=True,
            sandbox=True,
        )
        print(f"✅ Risposta API: {result}")
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error {e.response.status_code}: {e.response.text}")
    except ValueError as e:
        print(f"❌ Errore di configurazione: {e}")
    except Exception as e:
        print(f"❌ Errore generico: {e}")


if __name__ == "__main__":
    asyncio.run(test_purchase())
