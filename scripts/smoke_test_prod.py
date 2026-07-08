"""
Smoke test per l'applicazione Fidelitree in produzione.
Verifica che API, database e pagine principali siano operativi.

Utilizzo:
    python scripts/smoke_test_prod.py [URL_BASE] [ADMIN_SECRET_KEY]

Esempio:
    python scripts/smoke_test_prod.py https://fidelitree-app.ondigitalocean.app mia_chiave_segreta
"""

import os
import random
import sys

import requests


def run_smoke_test(base_url: str, admin_key: str) -> bool:
    print(f"--- Avvio Smoke Test su: {base_url} ---")
    headers = {"X-Admin-Key": admin_key}

    # 1. Health Check
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        resp.raise_for_status()
        if resp.json().get("status") == "ok":
            print("[OK] Health check passato")
        else:
            print("[FAIL] Health check ha risposto con dati inattesi")
            return False
    except Exception as e:
        print(f"[ERROR] Health check fallito: {e}")
        return False

    # 2. Pagine web principali
    for page in ["/download_card", "/merchant/login"]:
        try:
            resp = requests.get(f"{base_url}{page}", timeout=10)
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                print(f"[OK] Pagina {page} raggiungibile")
            else:
                print(f"[FAIL] Pagina {page} ha risposto con status {resp.status_code}")
        except Exception as e:
            print(f"[ERROR] Errore sulla pagina {page}: {e}")

    # 3. Ciclo di vita merchant via API (crea -> leggi -> elimina)
    print("--- Test API & Database ---")
    m_id = None
    ok = True
    try:
        payload = {
            "business_name": "SMOKE TEST MERCHANT",
            "phone_number": "+39" + "".join(random.choices("0123456789", k=10)),
            "password": "testpassword",
        }

        resp = requests.post(f"{base_url}/api/merchant/", json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            m_id = resp.json().get("id")
            print(f"[OK] API Merchant: creazione riuscita (ID: {m_id})")
        else:
            print(f"[FAIL] API Merchant: creazione fallita ({resp.status_code}) - {resp.text}")
            return False

        resp = requests.get(f"{base_url}/api/merchant/{m_id}", headers=headers, timeout=10)
        if resp.status_code == 200:
            print("[OK] API Merchant: lettura riuscita")
        else:
            print("[FAIL] API Merchant: lettura fallita")
            ok = False

        # Gli endpoint admin devono rifiutare le richieste senza chiave
        resp = requests.get(f"{base_url}/api/merchant/{m_id}", timeout=10)
        if resp.status_code == 403:
            print("[OK] API Merchant: accesso senza chiave admin rifiutato")
        else:
            print(f"[FAIL] API Merchant: accesso senza chiave ha risposto {resp.status_code} (atteso 403)")
            ok = False

    except Exception as e:
        print(f"[ERROR] Test API/DB interrotto: {e}")
        ok = False
    finally:
        if m_id:
            try:
                requests.delete(f"{base_url}/api/merchant/{m_id}", headers=headers, timeout=10)
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
