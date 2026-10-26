"""
Smoke test per l'applicazione Fidelitree in produzione.
Verifica che API, database, pagine principali e PWA siano operativi.
NON pianta alberi: niente scan e niente chiusura del periodo (crea e cancella solo un merchant di prova).

Utilizzo:
    python scripts/smoke_test_prod.py [URL_BASE] [ADMIN_SECRET_KEY]

Esempio:
    python scripts/smoke_test_prod.py https://fidelitree-app.ondigitalocean.app mia_chiave_segreta
"""

import os
import random
import sys

import requests


def _is_html(resp) -> bool:
    """True se la risposta è 200 e di tipo HTML."""
    return resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", "")


def run_smoke_test(base_url: str, admin_key: str, http=requests) -> bool:
    """
    Esegue i controlli e ritorna True se passano tutti.
    `http` è il client HTTP (default `requests`): ha la stessa interfaccia di
    `fastapi.testclient.TestClient`, così il test può girare anche su un'app locale
    (in quel caso `base_url` è la stringa vuota).
    """
    print(f"--- Avvio Smoke Test su: {base_url or 'app locale'} ---")
    headers = {"X-Admin-Key": admin_key}
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        """Stampa l'esito di un controllo e ricorda se qualcuno è fallito."""
        nonlocal ok
        ok = ok and passed
        print(f"[{'OK' if passed else 'FAIL'}] {label}" + (f" - {detail}" if detail and not passed else ""))

    # 1. Health check con versione
    try:
        resp = http.get(f"{base_url}/health", timeout=10)
        data = resp.json()
        check("Health check", resp.status_code == 200 and data.get("status") == "ok", resp.text)
        check(f"Versione esposta ({data.get('version')})", bool(data.get("version")), resp.text)
    except Exception as e:
        print(f"[ERROR] Health check fallito: {e}")
        return False

    # 2. Pagine pubbliche (cliente e merchant) e PWA
    for page in ["/customer/login", "/merchant/login", "/merchant/register"]:
        try:
            resp = http.get(f"{base_url}{page}", timeout=10)
            check(f"Pagina {page} raggiungibile", _is_html(resp), f"status {resp.status_code}")
        except Exception as e:
            check(f"Pagina {page} raggiungibile", False, str(e))
    try:
        resp = http.get(f"{base_url}/sw.js", timeout=10)
        check("Service worker /sw.js con scope /merchant/", resp.status_code == 200
              and resp.headers.get("Service-Worker-Allowed") == "/merchant/", f"status {resp.status_code}")
        resp = http.get(f"{base_url}/static/manifest.webmanifest", timeout=10)
        check("Manifest PWA raggiungibile", resp.status_code == 200, f"status {resp.status_code}")
    except Exception as e:
        check("File PWA raggiungibili", False, str(e))

    # 3. Ciclo di vita merchant via API admin (crea -> leggi -> pagina join -> elimina)
    print("--- Test API & Database ---")
    m_id = None
    try:
        payload = {
            "business_name": "SMOKE TEST MERCHANT",
            "email": f"smoke-{random.randrange(10**9)}@fidelitree.invalid",
        }
        resp = http.post(f"{base_url}/api/merchant/", json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            check("API Merchant: creazione", False, f"status {resp.status_code} - {resp.text}")
            return False
        m_id = resp.json().get("id")
        check(f"API Merchant: creazione (ID: {m_id})", True)

        resp = http.get(f"{base_url}/api/merchant/{m_id}", headers=headers, timeout=10)
        check("API Merchant: lettura", resp.status_code == 200, f"status {resp.status_code}")

        resp = http.get(f"{base_url}/join/{m_id}", timeout=10)
        check("Pagina /join/{id} del negozio", _is_html(resp), f"status {resp.status_code}")

        # Gli endpoint admin devono rifiutare le richieste senza chiave
        resp = http.get(f"{base_url}/api/merchant/{m_id}", timeout=10)
        check("API Merchant: accesso senza chiave admin rifiutato", resp.status_code == 403,
              f"status {resp.status_code} (atteso 403)")
        resp = http.get(f"{base_url}/api/merchant/", timeout=10)
        check("API Merchant: lista senza chiave admin rifiutata", resp.status_code == 403,
              f"status {resp.status_code} (atteso 403)")
    except Exception as e:
        check("Test API/DB", False, f"interrotto: {e}")
    finally:
        if m_id:
            try:
                http.delete(f"{base_url}/api/merchant/{m_id}", headers=headers, timeout=10)
                print("[OK] Pulizia merchant di test completata")
            except Exception:
                print("[WARN] Impossibile eliminare il merchant di test")

    print("\n--- Smoke Test Completato ---")
    return ok


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("PROD_URL", "http://localhost:8000")
    key = sys.argv[2] if len(sys.argv) > 2 else os.getenv("ADMIN_SECRET_KEY", "")

    success = run_smoke_test(url, key)
    sys.exit(0 if success else 1)
