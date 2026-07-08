"""
Test di rendering delle pagine HTML (Jinja2).
"""


def test_pagina_download(client):
    resp = client.get("/download_card")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_pagina_login(client):
    resp = client.get("/merchant/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_pagina_card(client, card, merchant):
    resp = client.get(f"/card/{card.id}")
    assert resp.status_code == 200
    assert merchant.business_name in resp.text
    assert "qrcode" in resp.text  # container del QR code


def test_pagina_card_inesistente(client):
    import uuid
    resp = client.get(f"/card/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_scanner_richiede_login(client):
    resp = client.get("/merchant/scanner")
    assert resp.status_code == 401


def test_scanner_con_login(auth_client):
    resp = auth_client.get("/merchant/scanner")
    assert resp.status_code == 200
    assert "html5-qrcode" in resp.text


def test_gestione_card_richiede_login(client, card):
    resp = client.get(f"/merchant/card/{card.id}/manage")
    assert resp.status_code == 401


def test_gestione_card_con_login(auth_client, card):
    resp = auth_client.get(f"/merchant/card/{card.id}/manage")
    assert resp.status_code == 200
    assert "Cashback" in resp.text
