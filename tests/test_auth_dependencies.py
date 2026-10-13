"""Test delle dependency di autenticazione con route di prova (SQLite in-memory, provider dev)."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import AuthIdentity, dev_user_id
from app.core.dependencies import (
    get_current_customer, get_current_merchant, get_session,
)
from sqlmodel import select

from app.models.models import Customer
from app.services.db_crud import customer_crud
from tests.conftest import login_as


@pytest.fixture()
def api(session, auth_provider):
    """App minima con una route per ogni dependency."""
    app = FastAPI()

    @app.get("/m")
    def m(merchant=Depends(get_current_merchant)):
        return {"id": merchant.id}

    @app.get("/c")
    def c(customer=Depends(get_current_customer)):
        return {"id": customer.id}

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def _identity(email: str) -> AuthIdentity:
    return AuthIdentity(user_id=dev_user_id(email), email=email)


def test_senza_cookie_401(api):
    assert api.get("/m").status_code == 401


def test_cookie_invalido_401(api):
    api.cookies.set("access_token", "spazzatura")
    assert api.get("/m").status_code == 401


def test_token_valido_senza_merchant_403(api):
    login_as(api, _identity("sconosciuto@test.it"))
    resp = api.get("/m")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account non registrato come esercente"


def test_token_valido_di_merchant_ritorna_il_merchant(api, session, merchant):
    merchant.auth_user_id = dev_user_id(merchant.email)
    session.add(merchant)
    session.commit()
    login_as(api, _identity(merchant.email))
    resp = api.get("/m")
    assert resp.status_code == 200
    assert resp.json()["id"] == merchant.id


def test_header_bearer_come_il_cookie(api, session, merchant, auth_provider):
    merchant.auth_user_id = dev_user_id(merchant.email)
    session.add(merchant)
    session.commit()
    token = auth_provider.issue_token(_identity(merchant.email))
    assert api.get("/m", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert api.get("/m", headers={"Authorization": "Bearer spazzatura"}).status_code == 401
    assert api.get("/m", headers={"Authorization": "Basic xyz"}).status_code == 401


def test_customer_creato_al_primo_accesso_e_poi_riusato(api, session):
    assert api.get("/c").status_code == 401

    login_as(api, _identity("cliente@test.it"))
    first = api.get("/c")
    assert first.status_code == 200
    customer = customer_crud.get_customer_by_email(session, "cliente@test.it")
    assert customer.auth_user_id == dev_user_id("cliente@test.it")
    assert first.json()["id"] == customer.id

    assert api.get("/c").json()["id"] == customer.id
    assert len(session.exec(select(Customer)).all()) == 1
