"""
Operazioni CRUD sulle campagne promozionali (tabella `campaign`).
"""

from datetime import datetime

from sqlalchemy import update
from sqlmodel import Session, select

from app.models.models import Campaign


def list_campaigns_by_merchant(session: Session, merchant_id: int) -> list[Campaign]:
    """
    Campagne del negozio nell'ordine della lista admin (D11): prima le non archiviate, poi le archiviate;
    dentro ciascun gruppo `created_at` decrescente e, a parità, `id` decrescente.
    """
    statement = (
        select(Campaign)
        .where(Campaign.merchant_id == merchant_id)
        .order_by(Campaign.is_archived, Campaign.created_at.desc(), Campaign.id.desc())
    )
    return list(session.exec(statement).all())


def list_active_campaigns_by_merchant(session: Session, merchant_id: int) -> list[Campaign]:
    """Campagne non archiviate del negozio: le sole che contano per il confronto delle parole chiave (AC-03)."""
    statement = select(Campaign).where(Campaign.merchant_id == merchant_id, Campaign.is_archived == False)  # noqa: E712
    return list(session.exec(statement).all())


def get_campaign(session: Session, campaign_id: int) -> Campaign | None:
    """Campagna per id, `None` se non esiste. Il controllo del negozio proprietario spetta al service."""
    return session.get(Campaign, campaign_id)


def update_campaign_fields(
    session: Session,
    campaign: Campaign,
    name: str,
    keyword: str,
    promo_text: str,
    value_cents: int,
    request_limit: int | None,
) -> Campaign:
    """
    Sostituisce i cinque campi modificabili della campagna (AC-04) e la ritorna aggiornata.

    Contatori, `is_archived` e `created_at` non si toccano.
    """
    campaign.name = name
    campaign.keyword = keyword
    campaign.promo_text = promo_text
    campaign.value_cents = value_cents
    campaign.request_limit = request_limit
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def set_campaign_archived(session: Session, campaign: Campaign, is_archived: bool) -> Campaign:
    """Imposta il flag di archiviazione della campagna (AC-05, AC-06) e la ritorna aggiornata."""
    campaign.is_archived = is_archived
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def archive_active_campaigns_by_merchant(session: Session, merchant_id: int) -> int:
    """
    Archivia con un solo UPDATE tutte le campagne non archiviate del negozio (AC-08) e ritorna quante sono.

    NON fa commit: l'archiviazione deve stare nella stessa transazione del cambio di stato del negozio,
    il commit lo fa il chiamante (`merchant_crud.update_merchant`).
    """
    statement = (
        update(Campaign)
        .where(Campaign.merchant_id == merchant_id, Campaign.is_archived == False)  # noqa: E712
        .values(is_archived=True)
    )
    return session.execute(statement).rowcount


def delete_campaign(session: Session, campaign: Campaign) -> None:
    """Cancella la riga della campagna, contatori compresi. Il controllo del proprietario spetta al service."""
    session.delete(campaign)
    session.commit()


def create_campaign(
    session: Session,
    merchant_id: int,
    name: str,
    keyword: str,
    promo_text: str,
    value_cents: int,
    request_limit: int | None,
    created_at: datetime,
) -> Campaign:
    """
    Inserisce una campagna non archiviata con i tre contatori a 0 (AC-02) e la ritorna aggiornata.

    Nessun default lato DB: i valori iniziali li scrive qui l'app. `created_at` arriva dal chiamante
    (UTC aware) perché il tempo non si legge dentro il crud.
    """
    campaign = Campaign(
        merchant_id=merchant_id,
        name=name,
        keyword=keyword,
        promo_text=promo_text,
        value_cents=value_cents,
        request_limit=request_limit,
        is_archived=False,
        dm_requests=0,
        comment_requests=0,
        uses=0,
        created_at=created_at,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign
