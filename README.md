# Fidelitree

Micro-SaaS di **carte fedeltà digitali che piantano alberi veri** per piccoli negozi: il cliente ha un wallet
(PWA) con cashback e *tree points*; i punti di tutti i clienti di un negozio formano un **pool mensile** che, a fine
mese, diventa alberi piantati su Ecologi. Backend FastAPI + SQLModel, frontend Jinja2 + Vanilla JS, database PostgreSQL.

> 🤖 Lavori con un coding agent? Il punto di ingresso è **[AGENTS.md](AGENTS.md)**.

## Avvio locale

```bash
# 1. Ambiente virtuale
.venv\Scripts\activate            # Windows

# 2. Dipendenze
pip install -r requirements.txt

# 3. Configurazione (copia e compila)
copy .env.example .env

# 4. Avvio con hot-reload
python local_main.py
```

Per provare l'app con dati di prova senza toccare il database vero (reset + seed + accessi):
vedi **"Collaudo locale"** in [.agents/workflows/deploy.md](.agents/workflows/deploy.md).

## Test

```bash
python -m pytest
```

I test girano su SQLite in-memory: non toccano il database di produzione e non fanno chiamate di rete.

## Deploy

Deploy automatico su **DigitalOcean App Platform** (Dockerfile) a ogni push su `main`, con database PostgreSQL (Neon; Supabase in arrivo).
Procedura completa e variabili d'ambiente richieste: [.agents/workflows/deploy.md](.agents/workflows/deploy.md).
