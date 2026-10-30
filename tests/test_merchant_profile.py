"""
Test del profilo e delle impostazioni di conversione del merchant autenticato.

Lo scan e il pool sono coperti da tests/test_scan.py; la logica pura da tests/unit/.
"""


def test_me_richiede_login(client):
    assert client.get("/api/merchant/me").status_code == 401


def test_me_espone_configurazione_in_euro(auth_client):
    resp = auth_client.get("/api/merchant/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "merchant@test.it"
    assert data["conversion_enabled"] is True
    assert data["conversion_threshold"] == 50
    assert data["conversion_value_eur"] == 2.0
    assert "conversion_value_cents" not in data
    for removed in ("password", "ecologi_api_key", "mode", "tree_threshold", "monthly_tree_cap"):
        assert removed not in data


def test_update_settings(auth_client):
    resp = auth_client.put("/api/merchant/me/settings", json={
        "conversion_enabled": False,
        "conversion_threshold": 80,
        "conversion_value_eur": 3.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversion_enabled"] is False
    assert data["conversion_threshold"] == 80
    assert data["conversion_value_eur"] == 3.5


def test_update_settings_soglia_non_valida(auth_client):
    resp = auth_client.put("/api/merchant/me/settings", json={"conversion_threshold": 0})
    assert resp.status_code == 422


def test_update_settings_valore_non_valido(auth_client):
    resp = auth_client.put("/api/merchant/me/settings", json={"conversion_value_eur": 0})
    assert resp.status_code == 422
