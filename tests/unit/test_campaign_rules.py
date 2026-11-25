"""
Test del core puro delle regole di campagna (nessun DB, nessun mock).
v0.4.1, ticket 01, AC-04 (conflitto delle parole chiave) e AC-09 (stessa normalizzazione nel riconoscimento).
"""

from app.core.enums import ServiceState
from app.services.campaign_service import (
    CampaignKey,
    CampaignStatus,
    campaign_status,
    keyword_conflict,
    match_campaign,
    pause_begins,
    scanner_label,
)


def test_parola_chiave_confrontata_in_forma_normalizzata_con_carta_e_altre_campagne():
    """
    v0.4.1 AC-04: una parola chiave è libera (None), "riservata" (uguale alla parola della carta) o "in uso"
    (uguale a quella di un'altra campagna) confrontando le forme NORMALIZZATE, non quelle scritte; "riservata"
    vince su "in uso"; escludere il proprio id evita il conflitto con se stessa.
    AC-09: match_campaign usa la stessa normalizzazione, restituisce l'id della prima campagna che combacia
    e None per testo vuoto, solo punteggiatura o senza corrispondenza.
    I valori attesi sono scritti a mano dagli esempi del contract (§2 e §4), non ricalcolati.
    """
    # La forma salvata "BLACK-FRIDAY" si normalizza in "black friday", come "Black-Friday" digitata dopo.
    altre = [CampaignKey(id=1, keyword="BLACK-FRIDAY"), CampaignKey(id=2, keyword="NATALE")]

    # Parola della carta: maiuscole, accenti e punteggiatura non contano.
    assert keyword_conflict("carta", "CARTA", altre) == "riservata"
    assert keyword_conflict("Càrta!", "CARTA", altre) == "riservata"
    # Altra campagna con la stessa forma normalizzata.
    assert keyword_conflict("Black-Friday", "CARTA", altre) == "in uso"
    # Parola libera.
    assert keyword_conflict("PASQUA", "CARTA", altre) is None
    # Esclusa se stessa: la campagna 1 può riconfermare la propria parola.
    assert keyword_conflict("Black-Friday", "CARTA", altre, exclude_id=1) is None
    # L'esclusione vale solo per l'id indicato.
    assert keyword_conflict("Black-Friday", "CARTA", altre, exclude_id=2) == "in uso"
    # Se la parola è sia della carta sia di un'altra campagna, vince "riservata".
    con_carta = [CampaignKey(id=3, keyword="Carta")]
    assert keyword_conflict("CARTA", "carta", con_carta) == "riservata"

    # Riconoscimento: stessa normalizzazione, emoji e punteggiatura ignorate.
    assert match_campaign("BLACK-FRIDAY 🎄", altre) == 1
    assert match_campaign("natale", altre) == 2
    # Nessuna corrispondenza, testo vuoto, None o solo punteggiatura.
    assert match_campaign("pasqua", altre) is None
    assert match_campaign("", altre) is None
    assert match_campaign(None, altre) is None
    assert match_campaign("!!", altre) is None
    # Con due campagne che combaciano vince la prima della lista.
    doppie = [CampaignKey(id=7, keyword="Sconto"), CampaignKey(id=5, keyword="SCONTO!")]
    assert match_campaign("sconto", doppie) == 7


def test_stato_campagna_inizio_pausa_ed_etichetta_scanner():
    """
    v0.4.1 AC-01/AC-21: lo stato di una campagna si deriva da archiviazione e stato del negozio: archiviata
    vince sempre; altrimenti attiva solo con negozio ACTIVE, ferma con negozio in attesa o in pausa.
    AC-08: la pausa "inizia" solo se si arriva a PAUSED da uno stato diverso da PAUSED (tutte le 9 coppie),
    perché solo allora le campagne vanno archiviate.
    AC-23: l'etichetta del bottone mostra il valore in euro con due decimali e virgola solo se è > 0.
    I valori attesi sono scritti a mano dagli esempi del contract (§4), non ricalcolati.
    """
    # Archiviata: lo stato è ARCHIVED con qualunque stato del negozio.
    for stato in ServiceState:
        assert campaign_status(True, stato) == CampaignStatus.ARCHIVED
    # Non archiviata: dipende solo dal negozio.
    assert campaign_status(False, ServiceState.ACTIVE) == CampaignStatus.ACTIVE
    assert campaign_status(False, ServiceState.PENDING) == CampaignStatus.STOPPED
    assert campaign_status(False, ServiceState.PAUSED) == CampaignStatus.STOPPED

    # Tutte le 9 combinazioni: vera solo per le due che finiscono in PAUSED partendo da non PAUSED.
    attesi_veri = {
        (ServiceState.PENDING, ServiceState.PAUSED),
        (ServiceState.ACTIVE, ServiceState.PAUSED),
    }
    for prima in ServiceState:
        for dopo in ServiceState:
            assert pause_begins(prima, dopo) is ((prima, dopo) in attesi_veri)

    # Etichetta con valore: due decimali e virgola.
    assert scanner_label("Caffè", 250) == "Applica Caffè (+2,50 €)"
    assert scanner_label("Cena", 5000) == "Applica Cena (+50,00 €)"
    assert scanner_label("Omaggio", 5) == "Applica Omaggio (+0,05 €)"
    # Senza valore: solo il nome.
    assert scanner_label("Caffè", 0) == "Applica Caffè"
