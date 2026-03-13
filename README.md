# Fidelitree Backend

Il backend per la web-app Fidelitree. Sviluppato in Python con FastAPI e SQLModel.

## Avvio Locale

1. Attivare l'ambiente virtuale:
   ```bash
   .venv\Scripts\activate
   ```

2. Installare le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```

3. Assicurarsi di avere un file `.env` valido (copiato dal team/documentazione interna).

4. Avviare il server (`uvicorn`):
   ```bash
   uvicorn app.main:app --reload
   ```

## Deploy

Questo repository è ottimizzato per essere deployato su **Railway** (usando il Dockerfile incluso) con un database PostgreSQL hostato su **Neon**. 
Assicurarsi di iniettare le variabili d'ambiente corrette su Railway (inclusa `DATABASE_URL`).
