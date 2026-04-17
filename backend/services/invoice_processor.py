"""
Normalization layer — pure Python, no LLM.
Handles date parsing, amount normalization, field cleaning.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Optional


def normalize_amount(value: Optional[Any]) -> Optional[float]:
    """
    Parse European and US amount strings.
    Examples: '82,64' -> 82.64 | '1.240,00' -> 1240.0 | '1240.00' -> 1240.0
    """
    if value is None:
        return None
    s = str(value).strip().replace(" ", "")
    if not s:
        return None

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        dot_pos = s.rfind(".")
        comma_pos = s.rfind(",")
        if comma_pos > dot_pos:
            # European thousands: 1.240,00
            s = s.replace(".", "").replace(",", ".")
        else:
            # US thousands: 1,240.00
            s = s.replace(",", "")
    elif has_comma:
        parts = s.split(",")
        # If exactly 3 digits after single comma it is a thousands separator
        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return None


def normalize_date(value: Optional[str]) -> Optional[str]:
    """
    Normalize various date formats to ISO-8601 YYYY-MM-DD.
    European DD-MM-YYYY is assumed for ambiguous cases.
    """
    if not value:
        return None

    # Try unambiguous YYYY-first formats first
    unambiguous = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]
    # Then DD-MM-YYYY European formats (before MM-DD-YYYY)
    ambiguous_eu = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
    ]
    fallback = [
        "%m-%d-%Y",
        "%m/%d/%Y",
    ]

    for fmt in unambiguous + ambiguous_eu + fallback:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return value  # return as-is if none matched


def normalize_supplier_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    name = unicodedata.normalize("NFC", name.strip())
    name = re.sub(r"\s+", " ", name)
    return name


def normalize_tax_id(tax_id: Optional[str]) -> Optional[str]:
    if not tax_id:
        return None
    cleaned = tax_id.strip().upper()
    return cleaned if cleaned else None


def normalize_currency(currency: Optional[str]) -> str:
    return (currency or "EUR").strip().upper()


def normalize_country(country: Optional[str]) -> Optional[str]:
    if not country:
        return None
    return country.strip().upper()


def normalize_description(desc: Optional[str]) -> Optional[str]:
    if not desc:
        return None
    return re.sub(r"\s+", " ", desc.strip())


def normalize_invoice(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes raw OCR payload dict and returns fully normalized dict.
    All deterministic transformations happen here — no LLM involved.
    """
    return {
        "document_id": str(raw.get("document_id", "")).strip(),
        "supplier_name": normalize_supplier_name(raw.get("supplier_name")),
        "supplier_tax_id": normalize_tax_id(raw.get("supplier_tax_id")),
        "invoice_number": (raw.get("invoice_number") or "").strip() or None,
        "invoice_date": normalize_date(raw.get("invoice_date")),
        "currency": normalize_currency(raw.get("currency")),
        "base_amount": normalize_amount(raw.get("base_amount")),
        "tax_amount": normalize_amount(raw.get("tax_amount")),
        "total_amount": normalize_amount(raw.get("total_amount")),
        "description": normalize_description(raw.get("description")),
        "country": normalize_country(raw.get("country")),
        "raw_ocr_text": raw.get("raw_ocr_text"),
        "field_confidence": raw.get("field_confidence") or {},
    }
