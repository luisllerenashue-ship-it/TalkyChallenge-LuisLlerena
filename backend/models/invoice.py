import json
from datetime import datetime

from sqlalchemy import Column, String, Float, Text, DateTime, Index
from backend.db.connection import Base


class Invoice(Base):
    __tablename__ = "invoices"

    # Primary key = document_id from OCR
    id = Column(String, primary_key=True, index=True)

    # ── raw input ────────────────────────────────────────────────────────────
    raw_payload = Column(Text, nullable=False)

    # ── normalized fields ────────────────────────────────────────────────────
    supplier_name_normalized = Column(String)
    supplier_tax_id = Column(String, index=True)
    invoice_number = Column(String)
    invoice_date = Column(String)       # ISO-8601 YYYY-MM-DD
    currency = Column(String(3))
    base_amount = Column(Float)
    tax_amount = Column(Float)
    total_amount = Column(Float)
    description = Column(Text)
    country = Column(String(2))

    # ── processing state ─────────────────────────────────────────────────────
    # Values: pending | processing | resolved | failed
    status = Column(String, default="pending", index=True)

    # ── resolution result (JSON) ─────────────────────────────────────────────
    resolution = Column(Text, nullable=True)

    # ── export tracking ──────────────────────────────────────────────────────
    exported_at = Column(DateTime, nullable=True, index=True)

    # ── timestamps ───────────────────────────────────────────────────────────
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # ── error info ───────────────────────────────────────────────────────────
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_invoices_status_exported", "status", "exported_at"),
    )

    # ── helpers ──────────────────────────────────────────────────────────────
    def get_raw_payload(self) -> dict:
        return json.loads(self.raw_payload) if self.raw_payload else {}

    def get_resolution(self) -> dict | None:
        return json.loads(self.resolution) if self.resolution else None
