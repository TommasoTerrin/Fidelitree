import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    print(f"🚀 Avvio Fidelitree in locale su http://{settings.APP_HOST}:{settings.APP_PORT}")
    print("💡 Il reload automatico è ATTIVO. Salva i file per aggiornare l'app.")
    
    uvicorn.run(
        "app.main:app",  # Carica l'oggetto 'app' dal modulo 'app.main'
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,      # Riavvia l'app a ogni modifica dei file
        log_level="info"
    )
