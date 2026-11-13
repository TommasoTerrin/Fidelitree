"""
Schemi HTTP delle campagne promozionali (contract §9).
"""

from typing import Any

from pydantic import BaseModel

from app.services.campaign_service import CampaignRow


class CampaignRequest(BaseModel):
    """
    Corpo di creazione di una campagna (contract §9). Tutti i campi sono `Any = None`: tipi e
    limiti li controlla `campaign_service.validate_campaign_input`, che risponde 400 e non 422.
    """

    name: Any = None
    keyword: Any = None
    promo_text: Any = None
    value_eur: Any = None
    request_limit: Any = None


class CampaignsResponse(BaseModel):
    """Risposta della lista campagne di un negozio: `{"campaigns": [CampaignRow]}`."""

    campaigns: list[CampaignRow]
