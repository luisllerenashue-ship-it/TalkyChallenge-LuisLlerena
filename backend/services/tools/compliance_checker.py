"""
Tool: compliance_checker
Runs deterministic rule-based checks and returns flags + risk score.
Does NOT decide review_decision — that is the LLM's responsibility.
The LLM uses these flags as evidence for its decision.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class ComplianceChecker:
    # ── public interface ──────────────────────────────────────────────────────

    def check(
        self,
        supplier_tax_id: Optional[str],
        supplier_name: Optional[str],
        field_confidence: Optional[Dict[str, float]],
        description: Optional[str],
        historical_data: Optional[Dict[str, Any]] = None,
        reference_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Returns a dict with:
        - flags: list of rule violations
        - risk_score: float [0, 1] (higher = more uncertain)
        - has_high_severity: bool
        """
        flags: List[Dict[str, Any]] = []
        risk_score = 0.0

        # RR1: Missing tax ID
        if not supplier_tax_id:
            flags.append({
                "rule_id": "RR1",
                "severity": "medium",
                "message": (
                    "Supplier tax ID is missing. "
                    "Cannot perform exact supplier match — relies on name fuzzy match only."
                ),
            })
            risk_score += 0.20

        # RR2: Low OCR confidence on key fields
        fc = field_confidence or {}
        supplier_conf = fc.get("supplier_name", 1.0)
        desc_conf = fc.get("description", 1.0)
        tax_conf = fc.get("supplier_tax_id", 1.0)

        if supplier_conf < 0.60:
            flags.append({
                "rule_id": "RR2",
                "severity": "high",
                "message": (
                    f"OCR confidence for supplier_name is {supplier_conf:.2f} "
                    "(below 0.60 — high risk of misidentification)."
                ),
            })
            risk_score += 0.30
        elif supplier_conf < 0.75:
            flags.append({
                "rule_id": "RR2",
                "severity": "low",
                "message": (
                    f"OCR confidence for supplier_name is {supplier_conf:.2f} "
                    "(slightly below 0.75)."
                ),
            })
            risk_score += 0.10

        if desc_conf < 0.60:
            flags.append({
                "rule_id": "RR2",
                "severity": "medium",
                "message": (
                    f"OCR confidence for description is {desc_conf:.2f} "
                    "(below 0.60 — category inference may be unreliable)."
                ),
            })
            risk_score += 0.15

        if tax_conf < 0.40:
            flags.append({
                "rule_id": "RR2",
                "severity": "medium",
                "message": (
                    f"OCR confidence for supplier_tax_id is {tax_conf:.2f} "
                    "(very low — tax ID may be incorrect)."
                ),
            })
            risk_score += 0.15

        # RR3: Conflicting historical decisions
        if historical_data and historical_data.get("found"):
            decisions = historical_data.get("recent_decisions", [])
            if decisions and "needs_review" in decisions:
                auto_count = sum(1 for d in decisions if d == "auto_approve")
                review_count = sum(1 for d in decisions if d == "needs_review")
                if auto_count > 0 and review_count > 0:
                    flags.append({
                        "rule_id": "RR3",
                        "severity": "medium",
                        "message": (
                            f"Historical decisions are mixed: {auto_count} auto_approve, "
                            f"{review_count} needs_review. Supplier has a review history."
                        ),
                    })
                    risk_score += 0.15

        # RR4: Completely unknown supplier
        hist_found = (historical_data or {}).get("found", False)
        ref_found = (reference_data or {}).get("found", False)

        if not hist_found and not ref_found:
            flags.append({
                "rule_id": "RR4",
                "severity": "high",
                "message": (
                    "Supplier not found in historical records OR reference catalog. "
                    "Appears to be a new/unknown supplier — classification is uncertain."
                ),
            })
            risk_score += 0.35

        # Clamp
        risk_score = round(min(risk_score, 1.0), 3)

        return {
            "flags": flags,
            "risk_score": risk_score,
            "flag_count": len(flags),
            "has_high_severity": any(f["severity"] == "high" for f in flags),
            "missing_tax_id": not bool(supplier_tax_id),
            "unknown_supplier": not hist_found and not ref_found,
        }
