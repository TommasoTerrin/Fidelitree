"""
Test unit del filtro dei log di accesso: il token del link della carta (`/c/<token>`) e l'id opaco del
webhook (`/webhooks/zernio/<hook_id>`) non devono comparire nei log. Nessun DB, nessuna rete.
"""

import logging

import pytest

from app.core import logging_filters
from app.core.logging_filters import AccessLogMaskFilter, mask_sensitive_paths


def test_il_percorso_della_carta_diventa_asterischi():
    assert mask_sensitive_paths("GET /c/abc123 HTTP/1.1") == "GET /c/*** HTTP/1.1"


def test_il_percorso_del_webhook_diventa_asterischi():
    assert mask_sensitive_paths("POST /webhooks/zernio/xyz HTTP/1.1") == "POST /webhooks/zernio/*** HTTP/1.1"


def test_la_query_string_non_resta_attaccata_al_token():
    assert mask_sensitive_paths("/c/abc123?utm=1") == "/c/***?utm=1"


@pytest.mark.parametrize("path", [
    "/card/5b1c8f3e-0000-4000-8000-000000000000",
    "/merchant/card/5b1c8f3e-0000-4000-8000-000000000000/manage",
    "/static/manifest.webmanifest",
    "/static/c/qualcosa",
    "/merchant/scanner",
    "/privacy",
    "/c/",
    "/webhooks/zernio/",
])
def test_gli_altri_percorsi_restano_invariati(path):
    assert mask_sensitive_paths(path) == path
    assert mask_sensitive_paths(f"GET {path} HTTP/1.1") == f"GET {path} HTTP/1.1"


def test_testo_vuoto_resta_vuoto():
    assert mask_sensitive_paths("") == ""


def _record(msg, args=()) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, msg, args, None)


def test_il_filtro_maschera_un_record_con_solo_il_messaggio():
    record = _record("GET /c/abc123 HTTP/1.1")
    assert AccessLogMaskFilter().filter(record) is True
    assert record.getMessage() == "GET /c/*** HTTP/1.1"


def test_il_filtro_maschera_gli_argomenti_come_li_passa_uvicorn():
    """uvicorn logga `'%s - "%s %s HTTP/%s" %d'` con il percorso (con query) come terzo argomento."""
    record = _record('%s - "%s %s HTTP/%s" %d', ("10.0.0.1:5000", "GET", "/c/SEGRETO?x=1", "1.1", 200))
    assert AccessLogMaskFilter().filter(record) is True
    assert record.args[2] == "/c/***?x=1"
    assert record.args[4] == 200  # lo status resta un intero: `%d` non deve rompersi
    assert record.getMessage() == '10.0.0.1:5000 - "GET /c/***?x=1 HTTP/1.1" 200'
    assert "SEGRETO" not in record.getMessage()


def test_il_filtro_maschera_anche_il_webhook():
    record = _record('%s - "%s %s HTTP/%s" %d', ("10.0.0.1:5000", "POST", "/webhooks/zernio/HOOK-OPACO", "1.1", 200))
    AccessLogMaskFilter().filter(record)
    assert "HOOK-OPACO" not in record.getMessage()
    assert "/webhooks/zernio/***" in record.getMessage()


def test_il_filtro_non_tocca_i_record_senza_segreti():
    record = _record('%s - "%s %s HTTP/%s" %d', ("10.0.0.1:5000", "GET", "/merchant/scanner", "1.1", 200))
    AccessLogMaskFilter().filter(record)
    assert record.getMessage() == '10.0.0.1:5000 - "GET /merchant/scanner HTTP/1.1" 200'


def test_il_filtro_regge_argomenti_in_un_dizionario():
    record = _record("%(path)s", None)
    record.args = {"path": "/c/SEGRETO"}
    AccessLogMaskFilter().filter(record)
    assert record.getMessage() == "/c/***"


def test_installato_sul_logger_di_uvicorn_il_token_non_arriva_a_caplog(caplog):
    """Il controllo che conta: un record vero, loggato su `uvicorn.access`, esce mascherato."""
    logger = logging.getLogger("uvicorn.access")
    logging_filters.install_access_log_filter()
    try:
        with caplog.at_level(logging.INFO, logger="uvicorn.access"):
            logger.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1:5000", "GET", "/c/TOKEN-SEGRETO", "1.1", 200)
        assert "TOKEN-SEGRETO" not in caplog.text
        assert "/c/***" in caplog.text
    finally:
        logging_filters.remove_access_log_filter()


def test_l_installazione_e_idempotente():
    logger = logging.getLogger("uvicorn.access")
    before = [f for f in logger.filters if isinstance(f, AccessLogMaskFilter)]
    try:
        logging_filters.install_access_log_filter()
        logging_filters.install_access_log_filter()
        installed = [f for f in logger.filters if isinstance(f, AccessLogMaskFilter)]
        assert len(installed) == max(len(before), 1)
    finally:
        logging_filters.remove_access_log_filter()
    assert not [f for f in logger.filters if isinstance(f, AccessLogMaskFilter)]
