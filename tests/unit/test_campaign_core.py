"""
Test del core puro di `campaign_service` (nessun DB, nessun mock).
v0.4.1, ticket 01, AC-03 (prima fetta: validazione di `name` e `keyword`).
"""

import pytest

from app.core.errors import InvalidInputError
from app.services.campaign_service import validate_campaign_input


def _raw(**overrides):
    """Corpo grezzo valido per gli altri campi, così l'errore può venire solo da `name` o `keyword`."""
    raw = {"name": "Black Friday", "keyword": "BLACKFRIDAY", "promo_text": "Sconto del 10%",
           "value_eur": "5", "request_limit": None}
    raw.update(overrides)
    return raw


def test_nome_e_parola_chiave_validati_con_strip_e_senza_normalizzazione():
    """
    v0.4.1 AC-03: un nome o una parola chiave fuori dai limiti (decisione 12) o con spazi interni o vuota dopo la
    normalizzazione dà InvalidInputError, il cui messaggio non contiene il valore inviato; i valori validi
    escono con lo strip applicato e la parola chiave resta nella forma scritta ("Black-Friday", non
    "black friday"), perché la normalizzazione serve solo al confronto, non alla memorizzazione.
    """
    # Caso felice: strip ai lati, forma scritta della parola chiave intatta.
    ok = validate_campaign_input(_raw(name="  Black Friday  ", keyword="  Black-Friday  "))
    assert ok.name == "Black Friday"
    assert ok.keyword == "Black-Friday"

    # Estremi ammessi: nome di 3 e di 40 caratteri, parola chiave di 3 e di 30.
    assert validate_campaign_input(_raw(name="abc")).name == "abc"
    assert validate_campaign_input(_raw(name="n" * 40)).name == "n" * 40
    assert validate_campaign_input(_raw(keyword="abc")).keyword == "abc"
    assert validate_campaign_input(_raw(keyword="k" * 30)).keyword == "k" * 30

    # Valori non validi: (campo, valore). Il valore non deve comparire nel messaggio.
    non_validi = [
        ("name", "Zq"),                # 2 caratteri: sotto il minimo
        ("name", "  Zq  "),            # 2 caratteri solo dopo lo strip
        ("name", "n" * 41),            # sopra il massimo
        ("name", ""),                  # vuoto
        ("name", None),                # non è una stringa
        ("keyword", "Zq"),             # 2 caratteri: sotto il minimo
        ("keyword", "k" * 31),         # sopra il massimo
        ("keyword", "NATALE 2026"),    # spazio interno
        ("keyword", "NATALE\t2026"),   # altro carattere di spazio interno
        ("keyword", "!!!"),            # 3 caratteri ma vuota dopo normalize_text
        ("keyword", ""),               # vuota
        ("keyword", None),             # non è una stringa
    ]
    for campo, valore in non_validi:
        with pytest.raises(InvalidInputError) as errore:
            validate_campaign_input(_raw(**{campo: valore}))
        messaggio = str(errore.value)
        assert messaggio, f"{campo}={valore!r}: messaggio vuoto"
        if isinstance(valore, str) and valore.strip():
            assert valore.strip() not in messaggio, f"{campo}={valore!r}: il messaggio riporta il valore inviato"


def test_testo_promo_e_importo_validati_ai_limiti_della_decisione_12():
    """
    v0.4.1 AC-03: `promo_text` (1-850 caratteri dopo lo strip, a capo interni conservati) e `value_eur`
    (vuoto = 0; numero o stringa numerica con virgola o punto; 0-50,00 euro, cioè 0-5000 centesimi) fuori dai
    limiti o di tipo sbagliato danno sempre InvalidInputError (mai TypeError) e il messaggio non contiene il
    valore inviato. I centesimi attesi sono letterali fatti a mano ("2,50" euro sono 250 centesimi), non
    ricalcolati con la funzione di conversione del codice.
    """
    # promo_text valido: strip ai lati, a capo interni intatti.
    ok = validate_campaign_input(_raw(promo_text="  riga uno\n\nriga due \n"))
    assert ok.promo_text == "riga uno\n\nriga due"

    # Estremo ammesso: 850 caratteri, anche se circondati da spazi (lo strip viene prima del conteggio).
    assert validate_campaign_input(_raw(promo_text="p" * 850)).promo_text == "p" * 850
    assert validate_campaign_input(_raw(promo_text="  " + "p" * 850 + "  ")).promo_text == "p" * 850
    # Un solo carattere è il minimo ammesso.
    assert validate_campaign_input(_raw(promo_text=" x ")).promo_text == "x"

    # value_eur valido: (valore inviato, centesimi attesi).
    importi_validi = [
        ("2,50", 250),       # virgola decimale
        ("2.50", 250),       # punto decimale
        ("5", 500),          # stringa intera
        (5, 500),            # int
        (2.5, 250),          # float
        (0, 0),              # zero numerico
        ("0", 0),            # zero come stringa
        (50, 5000),          # massimo ammesso: 50,00 euro
        ("50,00", 5000),     # massimo come stringa
        (None, 0),           # nessun importo
        ("", 0),             # campo vuoto del form
    ]
    for valore, centesimi in importi_validi:
        assert validate_campaign_input(_raw(value_eur=valore)).value_cents == centesimi, f"value_eur={valore!r}"

    # Chiave assente: come None, nessun importo.
    senza_importo = _raw()
    del senza_importo["value_eur"]
    assert validate_campaign_input(senza_importo).value_cents == 0

    # Valori non validi: (campo, valore). Nessuno deve dare TypeError e il valore non deve stare nel messaggio.
    non_validi = [
        ("promo_text", "t" * 851),                 # sopra il massimo
        ("promo_text", "  " + "t" * 851 + "  "),   # sopra il massimo anche dopo lo strip
        ("promo_text", ""),                        # vuoto
        ("promo_text", "   \n\t "),                # solo spazi
        ("promo_text", None),                      # non è una stringa
        ("promo_text", 12345),                     # non è una stringa
        ("promo_text", ["testo"]),                 # non è una stringa
        ("value_eur", 50.01),                      # sopra 50,00 euro
        ("value_eur", "50,01"),                    # sopra il massimo, virgola
        ("value_eur", "50.01"),                    # sopra il massimo, punto
        ("value_eur", 51),                         # sopra il massimo
        ("value_eur", -1),                         # negativo
        ("value_eur", "-2,50"),                    # negativo come stringa
        ("value_eur", True),                       # bool non è un numero
        ("value_eur", False),                      # bool non è un numero
        ("value_eur", float("nan")),               # non finito
        ("value_eur", float("inf")),               # non finito
        ("value_eur", "nan"),                      # non finito come stringa
        ("value_eur", "inf"),                      # non finito come stringa
        ("value_eur", "zzz-non-numerico"),         # non numerico
        ("value_eur", "2,50 euro"),                # numero con testo attorno
        ("value_eur", ["5"]),                      # tipo sbagliato
        ("value_eur", {"euro": 5}),                # tipo sbagliato
    ]
    for campo, valore in non_validi:
        with pytest.raises(InvalidInputError) as errore:
            validate_campaign_input(_raw(**{campo: valore}))
        messaggio = str(errore.value)
        assert messaggio, f"{campo}={valore!r}: messaggio vuoto"
        if isinstance(valore, (str, int, float)) and not isinstance(valore, bool):
            inviato = valore.strip() if isinstance(valore, str) else repr(valore)
            if len(inviato) >= 4:
                assert inviato not in messaggio, f"{campo}: il messaggio riporta il valore inviato"


def test_limite_richieste_e_corpo_non_dict_validati_ai_limiti_della_decisione_12():
    """
    v0.4.1 AC-03: `request_limit` vuoto (None, "" o assente) vuol dire nessun limite (None); un intero (non bool)
    o una stringa di sole cifre >= 1 esce come int; 0, negativi, float con parte decimale, bool, stringhe non
    di sole cifre e tipi sbagliati danno InvalidInputError (mai TypeError) senza il valore inviato nel messaggio.
    Un `raw` che non è un dict dà InvalidInputError. Un corpo completo e valido restituisce tutti e cinque i
    campi: i valori attesi sono letterali scritti a mano, non ricavati dalla funzione.
    """
    # Corpo completo e valido: tutti e cinque i campi, con il limite come stringa di cifre.
    completo = validate_campaign_input({"name": "Black Friday", "keyword": "BLACKFRIDAY",
                                        "promo_text": "Sconto del 10%", "value_eur": "2,50",
                                        "request_limit": "100"})
    assert completo.name == "Black Friday"
    assert completo.keyword == "BLACKFRIDAY"
    assert completo.promo_text == "Sconto del 10%"
    assert completo.value_cents == 250
    assert completo.request_limit == 100

    # Limiti validi: (valore inviato, limite atteso).
    limiti_validi = [
        (None, None),     # nessun limite
        ("", None),       # campo vuoto del form
        (1, 1),           # minimo ammesso, int
        ("1", 1),         # minimo ammesso, stringa di cifre
        (250, 250),       # int
        ("250", 250),     # stringa di cifre
    ]
    for valore, atteso in limiti_validi:
        risultato = validate_campaign_input(_raw(request_limit=valore)).request_limit
        assert risultato == atteso, f"request_limit={valore!r}"
        if atteso is not None:
            assert type(risultato) is int, f"request_limit={valore!r}: non è un int"

    # Chiave assente: come None, nessun limite.
    senza_limite = _raw()
    del senza_limite["request_limit"]
    assert validate_campaign_input(senza_limite).request_limit is None

    # Limiti non validi: nessuno deve dare TypeError e il valore non deve stare nel messaggio.
    non_validi = [
        0,                 # zero: sotto il minimo
        "0",               # zero come stringa
        -1,                # negativo
        "-5",              # negativo come stringa (non di sole cifre)
        2.5,               # float con parte decimale
        "2.5",             # stringa con punto decimale
        "12abc",           # cifre e testo
        "abcdef",          # non numerico
        True,              # bool non è un intero
        False,             # bool non è un intero
        ["10"],            # tipo sbagliato
        {"limite": 10},    # tipo sbagliato
    ]
    for valore in non_validi:
        with pytest.raises(InvalidInputError) as errore:
            validate_campaign_input(_raw(request_limit=valore))
        messaggio = str(errore.value)
        assert messaggio, f"request_limit={valore!r}: messaggio vuoto"
        if isinstance(valore, (str, int, float)) and not isinstance(valore, bool):
            inviato = valore if isinstance(valore, str) else repr(valore)
            if len(inviato) >= 4:
                assert inviato not in messaggio, f"request_limit={valore!r}: il messaggio riporta il valore"

    # `raw` che non è un dict: sempre InvalidInputError, mai TypeError o AttributeError.
    for raw in [None, [], ["name", "keyword"], "name=Black Friday", 42]:
        with pytest.raises(InvalidInputError):
            validate_campaign_input(raw)
