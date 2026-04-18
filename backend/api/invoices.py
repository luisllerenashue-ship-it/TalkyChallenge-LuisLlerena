"""
REST endpoints for invoice ingestion, querying, and resolution.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import backend.config as config
from backend.db.connection import get_db
from backend.models.invoice import Invoice
from backend.models.schemas import InvoiceImportRequest, InvoiceInput
from backend.services.invoice_processor import normalize_invoice
from backend.services.llm_agent import InvoiceAgent

router = APIRouter(prefix="/invoices", tags=["invoices"])
logger = logging.getLogger(__name__)

_agent: InvoiceAgent | None = None


def _get_agent() -> InvoiceAgent:
    global _agent
    if _agent is None:
        _agent = InvoiceAgent()
    return _agent


# ── helpers ───────────────────────────────────────────────────────────────────

def _invoice_dict(invoice: Invoice) -> Dict[str, Any]:
    return {
        "id": invoice.id,
        "status": invoice.status,
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
        "resolution": invoice.get_resolution(),
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "resolved_at": invoice.resolved_at.isoformat() if invoice.resolved_at else None,
        "exported_at": invoice.exported_at.isoformat() if invoice.exported_at else None,
        "error_message": invoice.error_message,
    }


def _build_invoice(payload: Dict[str, Any]) -> Invoice:
    normalized = normalize_invoice(payload)
    return Invoice(
        id=payload["document_id"],
        raw_payload=json.dumps(payload, ensure_ascii=False),
        supplier_name_normalized=normalized["supplier_name"],
        supplier_tax_id=normalized["supplier_tax_id"],
        invoice_number=normalized["invoice_number"],
        invoice_date=normalized["invoice_date"],
        currency=normalized["currency"],
        base_amount=normalized["base_amount"],
        tax_amount=normalized["tax_amount"],
        total_amount=normalized["total_amount"],
        description=normalized["description"],
        country=normalized["country"],
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


# ── POST /invoices ─────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_invoice(payload: InvoiceInput, db: Session = Depends(get_db)):
    """Ingest a single post-OCR invoice."""
    existing = db.query(Invoice).filter(Invoice.id == payload.document_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Invoice '{payload.document_id}' already exists. "
                   "Use POST /invoices/{id}/override to update.",
        )

    invoice = _build_invoice(payload.model_dump())
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    logger.info("Created invoice %s", invoice.id)
    return _invoice_dict(invoice)


# ── POST /invoices/import ──────────────────────────────────────────────────────

@router.post("/import", status_code=201)
def import_invoices(request: InvoiceImportRequest, db: Session = Depends(get_db)):
    """Batch-import post-OCR invoices from a JSON array (idempotent)."""
    created: List[str] = []
    skipped: List[str] = []
    errors: List[Dict[str, Any]] = []

    for item in request.invoices:
        try:
            doc_id = item.document_id
            if db.query(Invoice).filter(Invoice.id == doc_id).first():
                skipped.append(doc_id)
                continue
            invoice = _build_invoice(item.model_dump())
            db.add(invoice)
            created.append(doc_id)
        except Exception as exc:
            errors.append({"document_id": item.document_id, "error": str(exc)})

    db.commit()
    logger.info(
        "Import complete: %d created, %d skipped, %d errors",
        len(created), len(skipped), len(errors),
    )
    return {
        "created": len(created),
        "skipped": len(skipped),
        "errors": len(errors),
        "created_ids": created,
        "skipped_ids": skipped,
        "error_details": errors,
    }


# ── POST /invoices/seed ────────────────────────────────────────────────────────

@router.post("/seed", status_code=201)
def seed_from_file(db: Session = Depends(get_db)):
    """
    Load and import all invoices from data/new_post_ocr_inputs.json.
    Useful for quick testing without calling /import manually.
    """
    seed_path = Path(config.HISTORICAL_DATA_PATH).parent / "new_post_ocr_inputs.json"
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail=f"Seed file not found: {seed_path}")

    with open(seed_path, "r", encoding="utf-8") as fh:
        seed_data = json.load(fh)

    created: List[str] = []
    skipped: List[str] = []
    errors: List[Dict[str, Any]] = []

    for item in seed_data:
        doc_id = item.get("document_id", "")
        try:
            if db.query(Invoice).filter(Invoice.id == doc_id).first():
                skipped.append(doc_id)
                continue
            invoice = _build_invoice(item)
            db.add(invoice)
            created.append(doc_id)
        except Exception as exc:
            errors.append({"document_id": doc_id, "error": str(exc)})

    db.commit()
    return {
        "created": len(created),
        "skipped": len(skipped),
        "errors": len(errors),
        "created_ids": created,
        "skipped_ids": skipped,
        "error_details": errors,
    }


# ── GET /invoices ──────────────────────────────────────────────────────────────

@router.get("")
def list_invoices(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List invoices with optional status filter (pending|processing|resolved|failed)."""
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    total = query.count()
    items = query.order_by(Invoice.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_invoice_dict(inv) for inv in items],
    }


# ── GET /invoices/{id} ────────────────────────────────────────────────────────

@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    """Get a single invoice and its resolution (if available)."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")
    return _invoice_dict(invoice)


# ── POST /invoices/{id}/resolve ───────────────────────────────────────────────

@router.post("/{invoice_id}/resolve")
def resolve_invoice(invoice_id: str, db: Session = Depends(get_db)):
    """
    Trigger LLM-based resolution for a single invoice.
    The agent calls three internal tools (historical_lookup, reference_validator,
    compliance_checker) and returns a structured resolution.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")

    if invoice.status == "resolved":
        return {
            "message": "Invoice already resolved. Use /override to correct.",
            "invoice": _invoice_dict(invoice),
        }

    # Mark as in-progress
    invoice.status = "processing"
    invoice.updated_at = datetime.utcnow()
    db.commit()

    try:
        agent = _get_agent()
        raw = invoice.get_raw_payload()
        normalized = normalize_invoice(raw)

        logger.info("Starting LLM resolution for %s", invoice_id)
        resolution = agent.resolve(normalized)

        invoice.resolution = json.dumps(resolution, ensure_ascii=False, default=str)
        invoice.status = "resolved"
        invoice.resolved_at = datetime.utcnow()
        invoice.updated_at = datetime.utcnow()
        invoice.error_message = None

    except Exception as exc:
        logger.error("Resolution failed for %s: %s", invoice_id, exc)
        invoice.status = "failed"
        invoice.error_message = str(exc)
        invoice.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail=f"Resolution failed: {exc}")

    db.commit()
    db.refresh(invoice)
    logger.info(
        "Resolved %s → decision=%s confidence=%.2f",
        invoice_id,
        invoice.get_resolution().get("review_decision"),
        invoice.get_resolution().get("confidence", 0),
    )
    return _invoice_dict(invoice)


# ── POST /invoices/{id}/override ─────────────────────────────────────────────

@router.post("/{invoice_id}/override")
def override_resolution(
    invoice_id: str,
    correction: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Manually override or correct an invoice resolution.
    The corrected record will be re-exported on the next /exports/run call.
    Supports re-injection of corrections back into the system for future learning.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")

    existing = invoice.get_resolution() or {}
    existing.update(correction)
    existing["manually_overridden"] = True
    existing["overridden_at"] = datetime.utcnow().isoformat()

    invoice.resolution = json.dumps(existing, ensure_ascii=False, default=str)
    invoice.status = "resolved"
    invoice.resolved_at = datetime.utcnow()
    invoice.updated_at = datetime.utcnow()
    # Reset export flag so the corrected record is re-exported
    invoice.exported_at = None

    db.commit()
    db.refresh(invoice)
    logger.info("Override applied to invoice %s", invoice_id)
    return _invoice_dict(invoice)
