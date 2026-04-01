import logging
import sys
from app.core.utils.db_utils import reset_db_and_create_test_merchant

# Setup logging
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # Se chiamato con --force (es. dall'agente), procede direttamente
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        reset_db_and_create_test_merchant()
    else:
        confirm = input("ATTENZIONE: Questo script eliminerà TUTTI i dati dal database Neon. Sei sicuro? (s/n): ")
        if confirm.lower() == 's':
            reset_db_and_create_test_merchant()
            print("\n🚀 Database resettato e Merchant di test creato!")
        else:
            print("Operazione annullata.")
