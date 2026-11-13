"""
Test della migrazione SQL a mano (v0.4.1, ticket 01, AC-28).

Lo script `migrations/0001_campagne.sql` si applica a mano su Neon e non si
esegue mai su SQLite (`SERIAL` lì non è un id automatico): qui si controlla solo
che sia coerente con il modello `Campaign`.
"""

import re
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.models import Campaign

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "migrations" / "0001_campagne.sql"

# Colonne del modello Campaign scritte nel contract (§3), indipendenti dal DDL generato
COLONNE_ATTESE = [
    "id", "merchant_id", "name", "keyword", "promo_text", "value_cents",
    "request_limit", "is_archived", "dm_requests", "comment_requests",
    "uses", "created_at",
]


def _compatta(testo: str) -> str:
    """Spazi (anche a capo e tabulazioni) compattati in uno solo, maiuscole ignorate."""
    return re.sub(r"\s+", " ", testo).strip().lower()


def _definizioni_ddl_postgres() -> list[str]:
    """
    Ogni riga di definizione (colonna o vincolo) del `CREATE TABLE` che
    SQLAlchemy genera per PostgreSQL dal modello, già compattata e senza la
    virgola finale. Si scarta la riga di apertura e quella di chiusura.
    """
    ddl = str(CreateTable(Campaign.__table__).compile(dialect=postgresql.dialect()))
    righe = [_compatta(r) for r in ddl.strip().splitlines()]
    corpo = righe[1:-1]  # tra "create table campaign (" e ")"
    return [r.rstrip(",").strip() for r in corpo if r.strip(", ")]


def test_script_contiene_ogni_colonna_e_vincolo_del_modello_senza_alter():
    """
    AC-28: ogni definizione di colonna e di vincolo del DDL PostgreSQL generato
    dal modello `Campaign` compare nello script; lo script ha una sola
    `CREATE TABLE` (più l'indice su `merchant_id`) e nessun `ALTER`, `DROP` né
    `CREATE TYPE`. Il confronto è sul testo compattato perché lo script è
    scritto a mano e può avere un'impaginazione diversa; il DDL generato è la
    fonte del testo atteso (contract §10), la lista delle colonne è un
    letterale del contract (§3) che protegge da un modello a cui manca qualcosa.
    """
    script = _compatta(SCRIPT.read_text(encoding="utf-8"))

    definizioni = _definizioni_ddl_postgres()

    # Il DDL generato deve nominare tutte le 12 colonne del contract (guardia sul modello)
    for colonna in COLONNE_ATTESE:
        assert any(d.startswith(colonna + " ") for d in definizioni), (
            f"colonna {colonna} assente dal DDL generato dal modello"
        )
    # Più i vincoli: chiave primaria e chiave esterna con cancellazione a cascata
    assert "primary key (id)" in definizioni
    assert "foreign key(merchant_id) references merchant (id) on delete cascade" in definizioni

    # Ogni definizione generata compare nello script
    for definizione in definizioni:
        assert definizione in script, f"manca nello script: {definizione}"

    # Una sola CREATE TABLE, idempotente, e l'indice su merchant_id
    assert script.count("create table") == 1
    assert "create table if not exists campaign" in script
    assert "create index if not exists ix_campaign_merchant_id on campaign (merchant_id)".lower() in script

    # Nessuna modifica a tabelle o tipi esistenti, nessun default lato DB
    assert "alter" not in script
    assert "drop" not in script
    assert "create type" not in script
    assert "default" not in script
