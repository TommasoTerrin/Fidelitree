# Guida alla Struttura del Progetto - Fidelitree

Questa guida descrive l'organizzazione del codice e le responsabilità di ciascuna parte del progetto Fidelitree.

## Struttura delle Directory

### `/app`
Contiene il cuore dell'applicazione FastAPI.
- **`main.py`**: Punto di ingresso dell'applicazione. Configura FastAPI, i middleware, il database e include i router.
- **`core/`**: Configurazioni e utility centrali.
    - `config.py`: Gestione delle variabili d'ambiente e impostazioni globali.
    - `security.py`: Gestione di crittografia (Fernet), token JWT e validazione Telegram.
    - `dependencies.py`: Dipendenze FastAPI (es. sessione DB, autenticazione merchant).
    - `utils/`: Utility generiche, inclusa la gestione del database (`db_utils.py`).
- **`models/`**:
    - `models.py`: Definizione delle tabelle del database (Merchant, TreeCard) tramite SQLModel.
- **`schemas/`**:
    - Schemi Pydantic per la validazione dell'input/output delle API (Merchant, Card).
- **`services/`**:
    - Logica di business complessa (es. `card_service.py` per l'aggiunta punti e piantaggio alberi).
    - `db_crud/`: Operazioni pure di creazione, lettura, aggiornamento e cancellazione sul database.
    - Integrazioni esterne (Digital Humani, Ecologi).
    - `telegram_bot.py`: Logica del bot Telegram per l'interazione con gli esercenti.
- **`routes/`**:
    - `consumer/`: API e view HTML dedicate ai clienti finali.
    - `merchant/`: API, autenticazione e view HTML dedicate agli esercenti (login, scanner, gestione).
- **`templates/`**: Template HTML (Jinja2) organizzati per tipologia di utente.
- **`static/`**: File statici (CSS, JS, immagini).

### `/mcp_server`
Contiene l'implementazione del Model Context Protocol (MCP) per permettere all'IA di interagire con il sistema.

### `/tests`
Suite di test completi:
- `test_crud.py`: Test unitari per modelli e database.
- `tests_routes.py`: Test di integrazione per gli endpoint API.
- `test_views.py`: Verifica del rendering delle pagine HTML.
- `test_auth_telegram.py`: Test specifici per il flusso di login tramite Telegram.

### Script di Utilità (Root)
- `local_main.py`: Avvio rapido in locale con hot-reload.
- `reset_db.py`: Svuota e ricrea il database (da usare con cautela).
- `create_test_merchants.py`: Popola il database con dati di test reali/fittizi.
- `generate_test_links.py`: Genera link rapidi per testare il frontend.

## Flusso di Funzionamento

1.  **Esercente (Merchant)**: Si registra o effettua il login (anche via Telegram). Accede allo scanner per inquadrare il QR code del cliente.
2.  **Cliente (Consumer)**: Scarica la sua TreeCard digitale. Quando l'esercente scansiona la card, può aggiungere punti.
3.  **Riforestazione**: Al raggiungimento della soglia punti impostata dal merchant, il sistema chiama automaticamente le API esterne (Digital Humani) per piantare un albero a nome della card del cliente.
