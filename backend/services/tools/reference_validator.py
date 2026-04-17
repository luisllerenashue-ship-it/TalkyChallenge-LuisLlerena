"""
Tool: reference_validator
Validates supplier against the canonical reference catalog and returns
official names, aliases, typical categories and business units.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class ReferenceValidator:
    def __init__(self, data_path: str) -> None:
        with open(data_path, "r", encoding="utf-8") as fh:
            data: Dict[str, Any] = json.load(fh)

        self._suppliers: List[Dict[str, Any]] = data.get("canonical_suppliers", [])
        self._categories: List[str] = data.get("categories", [])
        self._business_units: List[str] = data.get("business_units", [])
        self._review_rules: List[Dict[str, Any]] = data.get("review_rules", [])
        self._country_hints: Dict[str, str] = {
            h["country"]: h["notes"] for h in data.get("country_hints", [])
        }

        # Indexes
        self._tax_id_index: Dict[str, Dict[str, Any]] = {
            s["supplier_tax_id"].upper(): s
            for s in self._suppliers
            if s.get("supplier_tax_id")
        }
        self._alias_index: Dict[str, Dict[str, Any]] = {}
        for s in self._suppliers:
            for alias in s.get("known_aliases", []):
                self._alias_index[alias.upper()] = s
            # Also index canonical name itself
            self._alias_index[s["canonical_supplier"].upper()] = s

    # ── public interface ──────────────────────────────────────────────────────

    def get_valid_categories(self) -> List[str]:
        return self._categories

    def get_valid_business_units(self) -> List[str]:
        return self._business_units

    def get_review_rules(self) -> List[Dict[str, Any]]:
        return self._review_rules

    def get_country_hint(self, country: str) -> Optional[str]:
        return self._country_hints.get((country or "").upper())

    def lookup_by_tax_id(self, tax_id: str) -> Optional[Dict[str, Any]]:
        return self._tax_id_index.get((tax_id or "").strip().upper())

    def lookup_by_alias(self, name: str) -> Optional[Dict[str, Any]]:
        """Exact alias match, then fuzzy with 0.75 threshold."""
        if not name:
            return None
        upper = name.upper()
        if upper in self._alias_index:
            return self._alias_index[upper]

        best_score = 0.0
        best_match: Optional[Dict[str, Any]] = None
        for alias, supplier in self._alias_index.items():
            score = _similarity(name, alias)
            if score > best_score:
                best_score = score
                best_match = supplier

        return best_match if best_score >= 0.75 else None

    def get_supplier_info(
        self,
        tax_id: Optional[str],
        supplier_name: Optional[str],
    ) -> Dict[str, Any]:
        supplier: Optional[Dict[str, Any]] = None
        match_method: Optional[str] = None

        if tax_id:
            supplier = self.lookup_by_tax_id(tax_id)
            if supplier:
                match_method = "tax_id"

        if not supplier and supplier_name:
            supplier = self.lookup_by_alias(supplier_name)
            if supplier:
                match_method = "alias_fuzzy"

        if not supplier:
            return {
                "found": False,
                "match_method": None,
                "canonical_supplier": None,
                "typical_category": None,
                "typical_business_unit": None,
                "known_aliases": [],
                "description_keywords": [],
                "valid_categories": self._categories,
                "valid_business_units": self._business_units,
            }

        return {
            "found": True,
            "match_method": match_method,
            "canonical_supplier": supplier.get("canonical_supplier"),
            "typical_category": supplier.get("typical_category"),
            "typical_business_unit": supplier.get("typical_business_unit"),
            "known_aliases": supplier.get("known_aliases", []),
            "description_keywords": supplier.get("description_keywords", []),
            "valid_categories": self._categories,
            "valid_business_units": self._business_units,
        }
