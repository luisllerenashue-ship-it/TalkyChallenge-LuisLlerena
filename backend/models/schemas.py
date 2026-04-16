from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Input schemas ─────────────────────────────────────────────────────────────

class InvoiceInput(BaseModel):
    document_id: str
    supplier_name: Optional[str] = None
    supplier_tax_id: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    currency: Optional[str] = "EUR"
    base_amount: Optional[str] = None
    tax_amount: Optional[str] = None
    total_amount: Optional[str] = None
    description: Optional[str] = None
    country: Optional[str] = None
    raw_ocr_text: Optional[str] = None
    field_confidence: Optional[Dict[str, float]] = None


class InvoiceImportRequest(BaseModel):
    invoices: List[InvoiceInput]


# ── Resolution schemas ────────────────────────────────────────────────────────

class ToolCallTrace(BaseModel):
    tool: str
    input: Dict[str, Any]
    output: Dict[str, Any]


class ResolutionResult(BaseModel):
    canonical_supplier: str
    predicted_spend_category: str
    predicted_business_unit: str
    review_decision: str                     # auto_approve | needs_review
    confidence: float = Field(ge=0.0, le=1.0)
    decision_explanation: str
    tool_calls_trace: Optional[List[Dict[str, Any]]] = None
    manually_overridden: Optional[bool] = None
    overridden_at: Optional[str] = None


# ── Response schemas ──────────────────────────────────────────────────────────

class InvoiceResponse(BaseModel):
    id: str
    status: str
    supplier_name_normalized: Optional[str]
    supplier_tax_id: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    currency: Optional[str]
    base_amount: Optional[float]
    tax_amount: Optional[float]
    total_amount: Optional[float]
    description: Optional[str]
    country: Optional[str]
    resolution: Optional[Dict[str, Any]]
    created_at: datetime
    resolved_at: Optional[datetime]
    exported_at: Optional[datetime]
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: int
    created_ids: List[str]
    skipped_ids: List[str]
    error_details: List[Dict[str, Any]]


class ExportRunResponse(BaseModel):
    exported_count: int
    export_timestamp: str
    message: str


class AnalyticsSummary(BaseModel):
    total_exported: int
    by_category: Dict[str, int]
    by_decision: Dict[str, int]
