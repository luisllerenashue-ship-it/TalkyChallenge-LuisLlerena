"""
Shared pytest fixtures.
Uses an in-memory SQLite database so tests never touch the real invoices.db.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.db.connection import Base, get_db
from backend.models.invoice import Invoice  # noqa: F401 — registers model with Base

# StaticPool ensures ALL sessions share ONE connection → in-memory tables persist
_TEST_DB_URL = "sqlite:///:memory:"
_engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    Base.metadata.drop_all(bind=_engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def client(setup_test_db):
    with TestClient(app) as c:
        yield c


# ── Sample payloads ───────────────────────────────────────────────────────────

SAMPLE_ORANGE = {
    "document_id": "test_orange_001",
    "supplier_name": "Orange Espana",
    "supplier_tax_id": "",               # empty → normalised to None
    "invoice_number": "F-TEST-001",
    "invoice_date": "2026/03/02",
    "currency": "EUR",
    "base_amount": "82,64",
    "tax_amount": "17,35",
    "total_amount": "99,99",
    "description": "Servicio movil empresa marzo 2026",
    "country": "ES",
    "field_confidence": {"supplier_name": 0.84, "supplier_tax_id": 0.35},
}

SAMPLE_UNKNOWN = {
    "document_id": "test_unknown_001",
    "supplier_name": "Acme Mysterious Corp",
    "supplier_tax_id": "",
    "invoice_number": "X-9999",
    "invoice_date": "2026-04-01",
    "currency": "EUR",
    "base_amount": "500.00",
    "tax_amount": "105.00",
    "total_amount": "605.00",
    "description": "Unspecified services",
    "country": "ES",
    "field_confidence": {"supplier_name": 0.55, "description": 0.50},
}
