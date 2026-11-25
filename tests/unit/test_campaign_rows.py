"""
Test del core puro delle righe di campagna (nessun DB, nessun mock).
v0.4.1, ticket 01, AC-01 (riga per /admin) e AC-21/AC-23 (campagne dello scanner con l'etichetta).
"""

from datetime import datetime, timezone

from app.core.enums import ServiceState
from app.models.models import Campaign
from app.services.campaign_service import (
    CampaignRow,
    CampaignStatus,
    RequestChannel,
    ScannerCampaign,
    campaign_row,
    scanner_label,
)


def test_riga_campagna_con_tutti_i_campi_stato_derivato_e_data_in_utc():
    """
    v0.4.1 AC-01: campaign_row espone tutti i campi della campagna senza alterarli, lo stato è derivato da
    archiviazione e stato del negozio (non è una colonna) e un created_at senza fuso diventa UTC aware, mentre
    uno già aware resta com'è. AC-21/AC-23: ScannerCampaign porta l'etichetta "Applica <nome> (+<euro> €)" con
    importo > 0 (250 centesimi -> "2,50", virgola e due decimali) e "Applica <nome>" con importo 0.
    I valori attesi sono scritti a mano dagli esempi del contract (§4), non ricalcolati dal codice.
    """
    # Costruita senza sessione né DB: il modello è usato come semplice contenitore di campi.
    campagna = Campaign(
        id=7,
        merchant_id=3,
        name="Black Friday",
        keyword="Black-Friday",
        promo_text="20% di sconto\ncon la carta",
        value_cents=250,
        request_limit=100,
        is_archived=False,
        dm_requests=4,
        comment_requests=2,
        uses=1,
        created_at=datetime(2026, 11, 12, 9, 30, 0),  # senza fuso, come la restituisce SQLite
    )

    riga = campaign_row(campagna, ServiceState.ACTIVE)

    assert isinstance(riga, CampaignRow)
    assert riga.id == 7
    assert riga.merchant_id == 3
    assert riga.name == "Black Friday"
    assert riga.keyword == "Black-Friday"  # forma scritta, mai normalizzata
    assert riga.promo_text == "20% di sconto\ncon la carta"
    assert riga.value_cents == 250
    assert riga.request_limit == 100
    assert riga.is_archived is False
    assert riga.dm_requests == 4
    assert riga.comment_requests == 2
    assert riga.uses == 1
    assert riga.status == CampaignStatus.ACTIVE
    # Il fuso mancante diventa UTC: stesso istante, ora aware.
    assert riga.created_at == datetime(2026, 11, 12, 9, 30, 0, tzinfo=timezone.utc)
    assert riga.created_at.utcoffset().total_seconds() == 0

    # Stato derivato: negozio in pausa -> ferma; archiviata -> archiviata anche con negozio attivo.
    assert campaign_row(campagna, ServiceState.PAUSED).status == CampaignStatus.STOPPED
    campagna.is_archived = True
    assert campaign_row(campagna, ServiceState.ACTIVE).status == CampaignStatus.ARCHIVED

    # Una data già aware resta com'è, senza spostamenti.
    campagna.created_at = datetime(2026, 11, 12, 9, 30, 0, tzinfo=timezone.utc)
    assert campaign_row(campagna, ServiceState.ACTIVE).created_at == datetime(
        2026, 11, 12, 9, 30, 0, tzinfo=timezone.utc
    )

    # Scanner: etichetta con importo e senza importo.
    # L'etichetta attesa è il letterale del contract; ScannerCampaign la porta insieme agli altri campi.
    etichetta = scanner_label("Black Friday", 250)
    assert etichetta == "Applica Black Friday (+2,50 €)"
    con_importo = ScannerCampaign(id=7, name="Black Friday", value_cents=250, label=etichetta)
    assert (con_importo.id, con_importo.name, con_importo.value_cents) == (7, "Black Friday", 250)
    assert con_importo.label == "Applica Black Friday (+2,50 €)"
    assert scanner_label("Natale", 0) == "Applica Natale"
    senza_importo = ScannerCampaign(id=8, name="Natale", value_cents=0, label=scanner_label("Natale", 0))
    assert senza_importo.label == "Applica Natale"

    # Il canale di richiesta ha i valori del contract.
    assert RequestChannel.DM.value == "dm"
    assert RequestChannel.COMMENT.value == "comment"
