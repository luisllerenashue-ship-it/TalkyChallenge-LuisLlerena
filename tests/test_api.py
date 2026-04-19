"""
Integration tests for the REST API.
Uses the in-memory DB fixture from conftest.py.
The /resolve endpoint is NOT tested here (requires ANTHROPIC_API_KEY and live LLM).
"""
from __future__ import annotations

import pytest
from tests.conftest import SAMPLE_ORANGE, SAMPLE_UNKNOWN


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "timestamp" in body


class TestCreateInvoice:
    def test_create_single(self, client):
        resp = client.post("/invoices", json=SAMPLE_ORANGE)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == SAMPLE_ORANGE["document_id"]
        assert body["status"] == "pending"
        assert body["invoice_date"] == "2026-03-02"     # normalised from 2026/03/02
        assert abs(body["base_amount"] - 82.64) < 0.01  # normalised from "82,64"
        assert body["supplier_tax_id"] is None           # "" → None

    def test_duplicate_returns_409(self, client):
        resp = client.post("/invoices", json=SAMPLE_ORANGE)
        assert resp.status_code == 409

    def test_create_unknown_supplier(self, client):
        resp = client.post("/invoices", json=SAMPLE_UNKNOWN)
        assert resp.status_code == 201


class TestGetInvoice:
    def test_get_existing(self, client):
        resp = client.get(f"/invoices/{SAMPLE_ORANGE['document_id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == SAMPLE_ORANGE["document_id"]

    def test_get_non_existing(self, client):
        resp = client.get("/invoices/does_not_exist_xyz")
        assert resp.status_code == 404


class TestListInvoices:
    def test_list_all(self, client):
        resp = client.get("/invoices")
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert body["total"] >= 2

    def test_list_by_status(self, client):
        resp = client.get("/invoices?status=pending")
        assert resp.status_code == 200
        body = resp.json()
        assert all(item["status"] == "pending" for item in body["items"])

    def test_pagination(self, client):
        resp = client.get("/invoices?limit=1&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 1


class TestBatchImport:
    def test_import_new(self, client):
        payload = {
            "invoices": [
                {
                    "document_id": "import_test_001",
                    "supplier_name": "AWS EMEA",
                    "supplier_tax_id": "LU26375245",
                    "invoice_date": "2026-04-04",
                    "currency": "EUR",
                    "base_amount": "1640.80",
                    "tax_amount": "0.00",
                    "total_amount": "1640.80",
                    "description": "Cloud compute and storage",
                    "country": "LU",
                },
                {
                    "document_id": "import_test_002",
                    "supplier_name": "WeWork Spain",
                    "supplier_tax_id": "ESA12345000",
                    "invoice_date": "2026-04-07",
                    "currency": "EUR",
                    "base_amount": "980.00",
                    "tax_amount": "205.80",
                    "total_amount": "1185.80",
                    "description": "Coworking monthly office fee",
                    "country": "ES",
                },
            ]
        }
        resp = client.post("/invoices/import", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["created"] == 2
        assert body["skipped"] == 0
        assert body["errors"] == 0

    def test_import_idempotent(self, client):
        payload = {
            "invoices": [
                {
                    "document_id": "import_test_001",
                    "supplier_name": "AWS EMEA",
                    "invoice_date": "2026-04-04",
                    "currency": "EUR",
                    "base_amount": "1640.80",
                    "total_amount": "1640.80",
                }
            ]
        }
        resp = client.post("/invoices/import", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["created"] == 0
        assert body["skipped"] == 1


class TestOverrideResolution:
    def test_override(self, client):
        # Set a resolution via override (simulates a manual correction)
        correction = {
            "canonical_supplier": "ORANGE ESPAGNE SA",
            "predicted_spend_category": "telecom",
            "predicted_business_unit": "it",
            "review_decision": "auto_approve",
            "confidence": 0.95,
            "decision_explanation": "Manually corrected by operator.",
        }
        resp = client.post(
            f"/invoices/{SAMPLE_ORANGE['document_id']}/override",
            json=correction,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "resolved"
        assert body["resolution"]["canonical_supplier"] == "ORANGE ESPAGNE SA"
        assert body["resolution"]["manually_overridden"] is True
        assert body["exported_at"] is None  # reset for re-export


class TestExports:
    def test_export_run(self, client):
        resp = client.post("/exports/run")
        assert resp.status_code == 200
        body = resp.json()
        assert "exported_count" in body
        assert body["exported_count"] >= 1  # at least the overridden Orange invoice

    def test_export_summary(self, client):
        resp = client.get("/exports/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_exported" in body
        assert "by_category" in body
        assert "by_decision" in body

    def test_second_export_yields_zero(self, client):
        # Nothing new to export after first run
        resp = client.post("/exports/run")
        assert resp.status_code == 200
        assert resp.json()["exported_count"] == 0
