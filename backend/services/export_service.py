"""
Export service — incremental export from operational SQLite to analytics SQLite.

The analytics DB is intentionally kept as a separate file (analytics.db)
to represent the separation between the operational and analytical layers.
It stores a denormalised flat table ready for reporting/training.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

import backend.config as config
from backend.models.invoice import Invoice

logger = logging.getLogger(__name__)

_ANALYTICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS resolved_invoices (
    id                      TEXT PRIMARY KEY,
    supplier_name_raw       TEXT,
    supplier_name_normalized TEXT,
    supplier_tax_id         TEXT,
    invoice_number          TEXT,
    invoice_date            TEXT,
    currency                TEXT,
    base_amount             REAL,
    tax_amount              REAL,
    total_amount            REAL,
    description             TEXT,
    country                 TEXT,
    canonical_supplier      TEXT,
    predicted_spend_category TEXT,
    predicted_business_unit TEXT,
    review_decision         TEXT,
    confidence              REAL,
    decision_explanation    TEXT,
    manually_overridden     INTEGER DEFAULT 0,
    resolved_at             TEXT,
    exported_at             TEXT
);
"""


class ExportService:
    def __init__(self) -> None:
        Path(config.ANALYTICAL_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(config.ANALYTICAL_DB_PATH)
        conn.execute(_ANALYTICS_SCHEMA)
        conn.commit()
        conn.close()

    # ── public interface ──────────────────────────────────────────────────────

    def export_pending(self, db: Session) -> int:
        """
        Export resolved invoices that have not been exported yet.
        Uses exported_at IS NULL as the incremental marker.
        Returns the number of newly exported records.
        """
        pending = (
            db.query(Invoice)
            .filter(Invoice.status == "resolved", Invoice.exported_at.is_(None))
            .all()
        )

        if not pending:
            logger.info("No pending exports.")
            return 0

        export_ts = datetime.utcnow()
        exported_count = 0

        conn = sqlite3.connect(config.ANALYTICAL_DB_PATH)
        try:
            for invoice in pending:
                resolution = invoice.get_resolution() or {}
                raw = invoice.get_raw_payload()

                row: Dict[str, Any] = {
                    "id": invoice.id,
                    "supplier_name_raw": raw.get("supplier_name"),
                    "supplier_name_normalized": invoice.supplier_name_normalized,
                    "supplier_tax_id": invoice.supplier_tax_id,
                    "invoice_number": invoice.invoice_number,
                    "invoice_date": invoice.invoice_date,
                    "currency": invoice.currency,
                    "base_amount": invoice.base_amount,
                    "tax_amount": invoice.tax_amount,
                    "total_amount": invoice.total_amount,
                    "description": invoice.description,
                    "country": invoice.country,
                    "canonical_supplier": resolution.get("canonical_supplier"),
                    "predicted_spend_category": resolution.get("predicted_spend_category"),
                    "predicted_business_unit": resolution.get("predicted_business_unit"),
                    "review_decision": resolution.get("review_decision"),
                    "confidence": resolution.get("confidence"),
                    "decision_explanation": resolution.get("decision_explanation"),
                    "manually_overridden": int(
                        bool(resolution.get("manually_overridden", False))
                    ),
                    "resolved_at": (
                        invoice.resolved_at.isoformat() if invoice.resolved_at else None
                    ),
                    "exported_at": export_ts.isoformat(),
                }

                conn.execute(
                    """
                    INSERT OR REPLACE INTO resolved_invoices (
                        id, supplier_name_raw, supplier_name_normalized, supplier_tax_id,
                        invoice_number, invoice_date, currency,
                        base_amount, tax_amount, total_amount, description, country,
                        canonical_supplier, predicted_spend_category, predicted_business_unit,
                        review_decision, confidence, decision_explanation,
                        manually_overridden, resolved_at, exported_at
                    ) VALUES (
                        :id, :supplier_name_raw, :supplier_name_normalized, :supplier_tax_id,
                        :invoice_number, :invoice_date, :currency,
                        :base_amount, :tax_amount, :total_amount, :description, :country,
                        :canonical_supplier, :predicted_spend_category, :predicted_business_unit,
                        :review_decision, :confidence, :decision_explanation,
                        :manually_overridden, :resolved_at, :exported_at
                    )
                    """,
                    row,
                )

                invoice.exported_at = export_ts
                exported_count += 1

            conn.commit()
            db.commit()
            logger.info("Exported %d invoices to analytics DB.", exported_count)

        except Exception as exc:
            conn.rollback()
            db.rollback()
            logger.error("Export failed: %s", exc)
            raise
        finally:
            conn.close()

        return exported_count

    def get_summary(self) -> Dict[str, Any]:
        """Return aggregate statistics from the analytics layer."""
        conn = sqlite3.connect(config.ANALYTICAL_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM resolved_invoices"
            ).fetchone()["cnt"]

            by_category = conn.execute(
                "SELECT predicted_spend_category, COUNT(*) AS cnt "
                "FROM resolved_invoices GROUP BY predicted_spend_category"
            ).fetchall()

            by_decision = conn.execute(
                "SELECT review_decision, COUNT(*) AS cnt "
                "FROM resolved_invoices GROUP BY review_decision"
            ).fetchall()

            by_bu = conn.execute(
                "SELECT predicted_business_unit, COUNT(*) AS cnt "
                "FROM resolved_invoices GROUP BY predicted_business_unit"
            ).fetchall()

        finally:
            conn.close()

        return {
            "total_exported": total,
            "by_category": {r["predicted_spend_category"]: r["cnt"] for r in by_category},
            "by_decision": {r["review_decision"]: r["cnt"] for r in by_decision},
            "by_business_unit": {r["predicted_business_unit"]: r["cnt"] for r in by_bu},
        }
