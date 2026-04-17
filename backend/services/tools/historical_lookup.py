"""
Tool: historical_lookup
Searches the historical resolved-invoices JSON for supplier matches.
Uses tax-ID exact match first, then fuzzy name match.
"""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class HistoricalLookup:
    def __init__(self, data_path: str) -> None:
        with open(data_path, "r", encoding="utf-8") as fh:
            self._records: List[Dict[str, Any]] = json.load(fh)

        # Index by tax_id for O(1) lookups
        self._tax_id_index: Dict[str, List[Dict[str, Any]]] = {}
        for r in self._records:
            tid = (r.get("supplier_tax_id") or "").upper()
            if tid:
                self._tax_id_index.setdefault(tid, []).append(r)

    # ── public interface ──────────────────────────────────────────────────────

    def lookup_by_tax_id(self, tax_id: str) -> List[Dict[str, Any]]:
        if not tax_id:
            return []
        return self._tax_id_index.get(tax_id.strip().upper(), [])

    def lookup_by_name(self, name: str, top_n: int = 5) -> List[Dict[str, Any]]:
        if not name:
            return []
        scored: List[tuple[float, Dict[str, Any]]] = []
        for r in self._records:
            raw_name = r.get("supplier_name_raw", "")
            canonical = r.get("canonical_supplier", "")
            score = max(_similarity(name, raw_name), _similarity(name, canonical))
            if score > 0.50:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_n]]

    def get_supplier_history(
        self,
        tax_id: Optional[str],
        supplier_name: Optional[str],
    ) -> Dict[str, Any]:
        """
        Returns aggregated historical data for a supplier.
        Priority: exact tax_id → fuzzy name.
        """
        matches: List[Dict[str, Any]] = []
        match_method: Optional[str] = None

        if tax_id:
            matches = self.lookup_by_tax_id(tax_id)
            if matches:
                match_method = "tax_id_exact"

        if not matches and supplier_name:
            matches = self.lookup_by_name(supplier_name)
            if matches:
                match_method = "name_fuzzy"

        if not matches:
            return {
                "found": False,
                "match_method": None,
                "match_count": 0,
                "canonical_supplier": None,
                "typical_category": None,
                "typical_business_unit": None,
                "recent_decisions": [],
                "avg_confidence": None,
                "sample_descriptions": [],
            }

        canonical_counts: Dict[str, int] = {}
        categories: Dict[str, int] = {}
        business_units: Dict[str, int] = {}
        decisions: List[str] = []
        confidences: List[float] = []
        sample_descs: List[str] = []

        for r in matches:
            cs = r.get("canonical_supplier") or "UNKNOWN"
            canonical_counts[cs] = canonical_counts.get(cs, 0) + 1

            cat = r.get("predicted_spend_category")
            if cat:
                categories[cat] = categories.get(cat, 0) + 1

            bu = r.get("predicted_business_unit")
            if bu:
                business_units[bu] = business_units.get(bu, 0) + 1

            decisions.append(r.get("review_decision") or "unknown")

            conf = r.get("confidence")
            if conf is not None:
                confidences.append(float(conf))

            desc = r.get("description")
            if desc and len(sample_descs) < 3:
                sample_descs.append(desc)

        best_canonical = max(canonical_counts, key=canonical_counts.get)
        best_category = max(categories, key=categories.get) if categories else None
        best_bu = max(business_units, key=business_units.get) if business_units else None
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else None

        return {
            "found": True,
            "match_method": match_method,
            "match_count": len(matches),
            "canonical_supplier": best_canonical,
            "typical_category": best_category,
            "typical_business_unit": best_bu,
            "recent_decisions": decisions[:5],
            "avg_confidence": avg_conf,
            "sample_descriptions": sample_descs,
        }
