"""
Popola il database con merchant, carte e movimenti di prova per il collaudo locale.

Crea 2 merchant approvati con identità del provider `dev`, 2 clienti Instagram finti (IGSID inventati,
solo l'indice cieco finisce nel DB) con la loro carta presso ciascun negozio e alcuni scan, così i
pool del mese partono da livelli diversi:
- Bar Demo: conversione attiva, soglie del pool basse, pool a livello oro;
- Forno Solo Alberi: conversione disattivata, soglie di default, pool sotto il bronzo.
I punti si aggiungono sempre con `card_service.add_tree_points` (mai a mano nel registro),
così movimenti e contatore `MerchantPool` restano coerenti.

Utilizzo (dalla root del progetto):
    python -m scripts.seed_db            # credenziali dei merchant e id delle carte
    python -m scripts.seed_db --links    # in più, il link /c/<token> di ogni carta

Funziona solo con `AUTH_PROVIDER=dev`. È idempotente: NON cancella i dati esistenti, crea solo
ciò che manca e non ripete gli scan di un negozio che ha già movimenti.
Accesso: merchant con email + `DEV_AUTH_PASSWORD`. Il cliente non ha accesso: la carta si apre solo con il
link segreto. Il token è un segreto anche per carte finte, quindi i link si stampano solo con `--links`
(solo su stdout, mai nei log). L'id della carta è invece il contenuto del QR dello scanner.
La stampa è ASCII-safe: su una console Windows cp1252 caratteri come la freccia darebbero `UnicodeEncodeError`.
"""

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.core.auth import AuthIdentity, dev_user_id
from app.core.clock import utc_now
from app.core.config import settings
from app.main import engine
from app.models.models import Card, Merchant, PointTransaction
from app.services import card_service, instagram_service
from app.services.db_crud import merchant_crud

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Clienti finti: nome -> IGSID inventato (mai un IGSID vero)
CUSTOMER_IGSIDS = {"anna": "igsid-seed-anna", "luca": "igsid-seed-luca"}

MERCHANTS = [
    {
        "business_name": "Bar Demo",
        "email": "demo@fidelitree.it",
        "type": "test",
        "is_approved": True,
        "conversion_enabled": True,
        "conversion_threshold": 50,
        "conversion_value_cents": 200,
        "bronze_threshold": 20,
        "silver_threshold": 60,
        "gold_threshold": 100,
        # (cliente, tree points): 60 convertono subito 50 punti in 2 €; pool = 105 → oro
        "scans": [("anna", 60), ("luca", 45)],
    },
    {
        "business_name": "Forno Solo Alberi",
        "email": "forno@fidelitree.it",
        "type": "test",
        "is_approved": True,
        "conversion_enabled": False,
        # pool = 30, sotto la soglia di bronzo di default → nessun livello
        "scans": [("anna", 30)],
    },
]


@dataclass
class SeedEntry:
    """Un merchant del seed con le carte dei clienti finti (chiave: nome del cliente)."""

    merchant: Merchant
    cards: dict[str, Card] = field(default_factory=dict)


def _require_dev_provider() -> None:
    """Solleva `RuntimeError` se il provider non è `dev`: il seed non deve toccare altri ambienti."""
    if settings.AUTH_PROVIDER != "dev":
        raise RuntimeError(
            "Il seed funziona solo con AUTH_PROVIDER=dev: con un provider reale gli account "
            "si creano dal provider, non da questo script."
        )


def _identity(email: str) -> AuthIdentity:
    """Identità del provider dev per `email` (stesso `user_id` che darà il login vero)."""
    return AuthIdentity(user_id=dev_user_id(email), email=email)


def _get_or_create_merchant(session: Session, data: dict) -> Merchant:
    """Merchant con quell'email: lo crea (collegato all'identità dev) se non esiste."""
    existing = merchant_crud.get_merchant_by_email(session, data["email"])
    if existing:
        logger.info("Merchant già presente: %s", existing.business_name)
        return existing
    fields = {k: v for k, v in data.items() if k != "scans"}
    fields["auth_user_id"] = _identity(data["email"]).user_id
    logger.info("Creato merchant: %s", data["business_name"])
    return merchant_crud.create_merchant(session, fields)


def _has_movements(session: Session, merchant_id: int) -> bool:
    """True se il negozio ha già almeno un movimento di punti (il seed non li ripete)."""
    return session.exec(
        select(PointTransaction.id).where(PointTransaction.merchant_id == merchant_id)
    ).first() is not None


def seed(session: Session, now: Optional[datetime] = None) -> list[SeedEntry]:
    """
    Crea merchant, carte dei clienti finti e scan di prova (vedi docstring del modulo) e ritorna
    una `SeedEntry` per merchant. Rieseguirlo non duplica nulla.
    Solleva `RuntimeError` se `AUTH_PROVIDER` non è `dev`.
    """
    _require_dev_provider()
    now = now or utc_now()

    entries = []
    for data in MERCHANTS:
        merchant = _get_or_create_merchant(session, data)
        entry = SeedEntry(merchant=merchant)
        for name, igsid in CUSTOMER_IGSIDS.items():
            card, _ = instagram_service.get_or_create_card(session, merchant, igsid)
            entry.cards[name] = card

        if _has_movements(session, merchant.id):
            logger.info("Scan già presenti per %s: non li ripeto", merchant.business_name)
        else:
            for name, points in data["scans"]:
                card_service.add_tree_points(session, merchant, entry.cards[name].id, points, now=now)
        entries.append(entry)
    return entries


def print_access(entries: list[SeedEntry], base_url: str, show_links: bool = False) -> None:
    """
    Stampa l'accesso merchant e gli id delle carte di prova (il contenuto del QR per lo scanner). Solo con
    `show_links` stampa anche il link segreto `/c/<token>` di ogni carta (`card_link_url`, quindi con
    `PUBLIC_BASE_URL`): il token non va in nessun altro posto. Solo caratteri ASCII.
    """
    print("\n--- ACCESSI DI PROVA ---")
    print(f"Merchant: {base_url}/merchant/login  -> email + password '{settings.DEV_AUTH_PASSWORD}'")
    for entry in entries:
        merchant = entry.merchant
        print(f"\nMERCHANT: {merchant.business_name} (id={merchant.id})")
        print(f"  Email:  {merchant.email}")
        for name, card in entry.cards.items():
            print(f"  Carta di {name}: id {card.id}")
            if show_links:
                print(f"    Link: {instagram_service.card_link_url(card)}")
    print("-------------------------\n")


def main(argv: Optional[list[str]] = None) -> None:
    """
    Esegue il seed sul DB di `DATABASE_URL` e stampa gli accessi (a sessione ancora aperta). `argv` si passa
    nei test; `--links` aggiunge i link `/c/<token>` delle carte.
    """
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_db", description="Seed del DB di collaudo.")
    parser.add_argument("--links", action="store_true", help="stampa anche il link segreto /c/<token> di ogni carta")
    args = parser.parse_args(argv)
    try:
        with Session(engine) as db_session:
            entries = seed(db_session)
            print_access(entries, f"http://{settings.APP_HOST}:{settings.APP_PORT}", show_links=args.links)
    except RuntimeError as e:
        raise SystemExit(f"ERRORE: {e}")


if __name__ == "__main__":
    main()
