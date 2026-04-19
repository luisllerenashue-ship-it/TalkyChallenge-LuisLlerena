"""Unit tests for the three internal agent tools (no LLM required)."""
import pytest
import backend.config as config
from backend.services.tools.historical_lookup import HistoricalLookup
from backend.services.tools.reference_validator import ReferenceValidator
from backend.services.tools.compliance_checker import ComplianceChecker


@pytest.fixture(scope="module")
def historical():
    return HistoricalLookup(config.HISTORICAL_DATA_PATH)


@pytest.fixture(scope="module")
def reference():
    return ReferenceValidator(config.REFERENCE_DATA_PATH)


@pytest.fixture(scope="module")
def compliance():
    return ComplianceChecker()


# ── HistoricalLookup ──────────────────────────────────────────────────────────

class TestHistoricalLookup:
    def test_tax_id_exact_match(self, historical):
        result = historical.get_supplier_history(
            tax_id="ESA82009812", supplier_name=None
        )
        assert result["found"] is True
        assert result["match_method"] == "tax_id_exact"
        assert result["canonical_supplier"] == "ORANGE ESPAGNE SA"
        assert result["typical_category"] == "telecom"

    def test_fuzzy_name_match(self, historical):
        result = historical.get_supplier_history(
            tax_id=None, supplier_name="Deloittee"
        )
        assert result["found"] is True
        assert "DELOITTE" in result["canonical_supplier"]

    def test_unknown_supplier_returns_not_found(self, historical):
        result = historical.get_supplier_history(
            tax_id="XX9999999", supplier_name="Totally Unknown Corp XYZ"
        )
        assert result["found"] is False
        assert result["canonical_supplier"] is None

    def test_tax_id_takes_priority_over_name(self, historical):
        result = historical.get_supplier_history(
            tax_id="LU26375245", supplier_name="Some random name"
        )
        assert result["found"] is True
        assert result["canonical_supplier"] == "AWS EMEA SARL"
        assert result["match_method"] == "tax_id_exact"

    def test_google_ads_france(self, historical):
        result = historical.get_supplier_history(
            tax_id="FR40303265045", supplier_name=None
        )
        assert result["found"] is True
        assert result["canonical_supplier"] == "GOOGLE ADS FRANCE"
        assert result["typical_business_unit"] == "marketing"


# ── ReferenceValidator ────────────────────────────────────────────────────────

class TestReferenceValidator:
    def test_lookup_by_tax_id(self, reference):
        info = reference.get_supplier_info(tax_id="ESA82009812", supplier_name=None)
        assert info["found"] is True
        assert info["canonical_supplier"] == "ORANGE ESPAGNE SA"
        assert info["typical_category"] == "telecom"

    def test_lookup_by_alias_exact(self, reference):
        info = reference.get_supplier_info(tax_id=None, supplier_name="StapIes Iberia")
        assert info["found"] is True
        assert info["canonical_supplier"] == "STAPLES IBERIA SA"

    def test_lookup_by_alias_fuzzy(self, reference):
        info = reference.get_supplier_info(tax_id=None, supplier_name="Micr0soft Ireland")
        assert info["found"] is True
        assert "MICROSOFT" in info["canonical_supplier"]

    def test_unknown_returns_not_found(self, reference):
        info = reference.get_supplier_info(
            tax_id="ZZ000000", supplier_name="Nonexistent Vendor LLC"
        )
        assert info["found"] is False

    def test_valid_categories_present(self, reference):
        cats = reference.get_valid_categories()
        assert "telecom" in cats
        assert "software" in cats
        assert "travel" in cats

    def test_valid_business_units_present(self, reference):
        bus = reference.get_valid_business_units()
        assert "it" in bus
        assert "marketing" in bus


# ── ComplianceChecker ─────────────────────────────────────────────────────────

class TestComplianceChecker:
    def test_missing_tax_id_flag(self, compliance):
        result = compliance.check(
            supplier_tax_id="",
            supplier_name="Some Co",
            field_confidence={"supplier_name": 0.90},
            description="Some service",
        )
        rule_ids = [f["rule_id"] for f in result["flags"]]
        assert "RR1" in rule_ids
        assert result["risk_score"] > 0

    def test_low_supplier_confidence_flag(self, compliance):
        result = compliance.check(
            supplier_tax_id="ESA123",
            supplier_name="Test",
            field_confidence={"supplier_name": 0.50},
            description="desc",
        )
        high_flags = [f for f in result["flags"] if f["severity"] == "high"]
        assert len(high_flags) > 0
        assert result["has_high_severity"] is True

    def test_unknown_supplier_flag(self, compliance):
        hist_not_found = {"found": False}
        ref_not_found = {"found": False}
        result = compliance.check(
            supplier_tax_id="",
            supplier_name="Completely Unknown Inc",
            field_confidence={},
            description="mystery",
            historical_data=hist_not_found,
            reference_data=ref_not_found,
        )
        rule_ids = [f["rule_id"] for f in result["flags"]]
        assert "RR4" in rule_ids
        assert result["unknown_supplier"] is True

    def test_clean_invoice_has_low_risk(self, compliance):
        hist_ok = {"found": True, "recent_decisions": ["auto_approve", "auto_approve"]}
        ref_ok = {"found": True}
        result = compliance.check(
            supplier_tax_id="ESA82009812",
            supplier_name="Orange Espagne SA",
            field_confidence={"supplier_name": 0.97, "supplier_tax_id": 0.98},
            description="Fiber internet headquarters",
            historical_data=hist_ok,
            reference_data=ref_ok,
        )
        assert result["risk_score"] < 0.30
        assert result["missing_tax_id"] is False

    def test_risk_score_clamped_to_one(self, compliance):
        result = compliance.check(
            supplier_tax_id="",
            supplier_name="Unknown",
            field_confidence={"supplier_name": 0.30, "description": 0.40, "supplier_tax_id": 0.10},
            description=None,
            historical_data={"found": False},
            reference_data={"found": False},
        )
        assert result["risk_score"] <= 1.0
