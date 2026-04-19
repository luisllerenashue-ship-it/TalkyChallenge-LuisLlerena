"""Unit tests for the normalisation layer (no LLM, no DB)."""
import pytest
from backend.services.invoice_processor import (
    normalize_amount,
    normalize_date,
    normalize_supplier_name,
    normalize_tax_id,
    normalize_currency,
    normalize_invoice,
)


class TestNormalizeAmount:
    def test_european_decimal_comma(self):
        assert normalize_amount("82,64") == pytest.approx(82.64)

    def test_european_thousands_dot_decimal_comma(self):
        assert normalize_amount("1.240,00") == pytest.approx(1240.0)

    def test_us_decimal_dot(self):
        assert normalize_amount("1240.00") == pytest.approx(1240.0)

    def test_us_thousands_comma(self):
        assert normalize_amount("1,240.00") == pytest.approx(1240.0)

    def test_plain_integer(self):
        assert normalize_amount("550") == pytest.approx(550.0)

    def test_none_returns_none(self):
        assert normalize_amount(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_amount("") is None

    def test_float_passthrough(self):
        assert normalize_amount(99.99) == pytest.approx(99.99)

    def test_zero(self):
        assert normalize_amount("0.00") == pytest.approx(0.0)


class TestNormalizeDate:
    def test_iso_format(self):
        assert normalize_date("2026-03-31") == "2026-03-31"

    def test_slash_format(self):
        assert normalize_date("2026/03/02") == "2026-03-02"

    def test_dd_mm_yyyy_european(self):
        # "03-04-2026" is DD-MM-YYYY in European context → April 3
        assert normalize_date("03-04-2026") == "2026-04-03"

    def test_dd_slash_mm_slash_yyyy(self):
        assert normalize_date("07/04/2026") == "2026-04-07"

    def test_none_returns_none(self):
        assert normalize_date(None) is None

    def test_unknown_format_passthrough(self):
        result = normalize_date("2026.04.01")
        assert result == "2026-04-01"


class TestNormalizeSupplierName:
    def test_strips_whitespace(self):
        assert normalize_supplier_name("  Orange  Espana  ") == "Orange Espana"

    def test_none_returns_none(self):
        assert normalize_supplier_name(None) is None

    def test_collapses_multiple_spaces(self):
        assert normalize_supplier_name("Google   Cloud   EMEA") == "Google Cloud EMEA"


class TestNormalizeTaxId:
    def test_uppercases(self):
        assert normalize_tax_id("esa82009812") == "ESA82009812"

    def test_strips_whitespace(self):
        assert normalize_tax_id("  IE6388047V  ") == "IE6388047V"

    def test_empty_returns_none(self):
        assert normalize_tax_id("") is None

    def test_none_returns_none(self):
        assert normalize_tax_id(None) is None


class TestNormalizeCurrency:
    def test_default_eur(self):
        assert normalize_currency(None) == "EUR"

    def test_uppercases(self):
        assert normalize_currency("eur") == "EUR"


class TestNormalizeInvoice:
    def test_full_orange_invoice(self):
        raw = {
            "document_id": "doc_new_001",
            "supplier_name": "Orange Espana",
            "supplier_tax_id": "",
            "invoice_number": "F-2026-0312",
            "invoice_date": "2026/03/02",
            "currency": "EUR",
            "base_amount": "82,64",
            "tax_amount": "17,35",
            "total_amount": "99,99",
            "description": "Servicio movil empresa marzo 2026",
            "country": "ES",
        }
        result = normalize_invoice(raw)
        assert result["invoice_date"] == "2026-03-02"
        assert result["base_amount"] == pytest.approx(82.64)
        assert result["total_amount"] == pytest.approx(99.99)
        assert result["supplier_tax_id"] is None
        assert result["country"] == "ES"

    def test_google_cloud_invoice(self):
        raw = {
            "document_id": "doc_new_002",
            "supplier_name": "Google C1oud EMEA",
            "supplier_tax_id": "IE6388047V",
            "invoice_date": "2026-03-31",
            "currency": "EUR",
            "base_amount": "1240.00",
            "tax_amount": "0.00",
            "total_amount": "1240.00",
            "description": "Compute engine and storage subscription March",
            "country": "IE",
        }
        result = normalize_invoice(raw)
        assert result["supplier_tax_id"] == "IE6388047V"
        assert result["base_amount"] == pytest.approx(1240.0)
        assert result["invoice_date"] == "2026-03-31"
