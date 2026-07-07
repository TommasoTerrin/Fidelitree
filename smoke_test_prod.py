import requests
import sys
import os
import uuid

"""
Script di Smoke Test per l'applicazione Fidelitree in produzione.
Verifica che i componenti principali (API, Database, Frontend) siano operativi.

Utilizzo:
    python smoke_test_prod.py [URL_BASE] [ADMIN_SECRET_KEY]

Esempio:
    python smoke_test_prod.py https://fidelitree-app.ondigitalocean.app mia_chiave_segreta
"""

def run_smoke_test(base_url, admin_key):
    print(f"--- Avvio Smoke Test su: {base_url} ---")
    
    # 1. Health Check
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        resp.raise_for_status()
        if resp.json().get("status") == "ok":
            print("[OK] Health check passato")
        else:
            print("[FAIL] Health check ha risposto con dati inattesi")
    except Exception as e:
        print(f"[ERROR] Health check fallito: {e}")
        return False

    # 2. Verifica Pagine Web principali
    pages = ["/download_card", "/merchant/login"]
    for page in pages:
        try:
            resp = requests.get(f"{base_url}{page}", timeout=10)
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                print(f"[OK] Pagina {page} raggiungibile")
            else:
                print(f"[FAIL] Pagina {page} ha risposto con status {resp.status_code}")
        except Exception as e:
            print(f"[ERROR] Erroresulla pagina {page}: {e}")

    # 3. Test API e Database (Ciclo di vita Merchant)
    print("--- Test API & Database ---")
    m_id = None
    try:
        # Crea un merchant di test
        payload = {
            "business_name": "SMOKE TEST MERCHANT",
            "phone_number": f"+39{uuid.uuid4().hex[:10]}",
            "password": "testpassword",
            "humami_api_key": "test",
            "humami_enterprise_id": "test"
        }
        headers = {"X-Admin-Token": admin_key}
        
        resp = requests.post(f"{base_url}/api/merchant/", json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            m_id = resp.json().get("id")
            print(f"[OK] API Merchant: Creazione riuscita (ID: {m_id})")
        else:
            print(f"[FAIL] API Merchant: Creazione fallita ({resp.status_code}) - {resp.text}")
            return False

        # Verifica lettura
        resp = requests.get(f"{base_url}/api/merchant/{m_id}", timeout=10)
        if resp.status_code == 200:
            print("[OK] API Merchant: Lettura riuscita")
        else:
            print("[FAIL] API Merchant: Lettura fallita")

    except Exception as e:
        print(f"[ERROR] Test API/DB interrotto: {e}")
    finally:
        # Pulizia
        if m_id:
            try:
                requests.delete(f"{base_url}/api/merchant/{m_id}", timeout=10)
                print("[OK] Pulizia merchant di test completata")
            except:
                print("[WARN] Impossibile eliminare il merchant di test")

    print("\n--- Smoke Test Completato ---")
    return True

if __name__ == "__main__":
    # Carica da argomenti o variabili d'ambiente
    url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("PROD_URL", "http://localhost:8000")
    key = sys.argv[2] if len(sys.argv) > 2 else os.getenv("ADMIN_SECRET_KEY", "your-admin-secret-key")
    
    success = run_smoke_test(url, key)
    sys.exit(0 if success else 1)
