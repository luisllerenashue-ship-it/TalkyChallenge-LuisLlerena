# Post-OCR Invoice Resolution Service

A backend service that receives structured post-OCR invoice payloads, normalises them, and uses an **LLM agent with internal tools** (Anthropic Claude) to resolve business fields: canonical supplier, spend category, business unit, and review decision. Resolved records are exported incrementally to a separate analytics layer.

---

## Architecture

```
POST /invoices  ──►  Normalisation layer  ──►  Operational DB (SQLite: invoices.db)
                          (pure Python)              │
                                                     │  POST /invoices/{id}/resolve
                                                     ▼
                                              LLM Agent (Claude)
                                                  │   │   │
                                    Tool 1: lookup_historical_supplier
                                    Tool 2: validate_against_reference
                                    Tool 3: check_compliance_flags
                                                     │
                                              Resolution JSON
                                              persisted to DB
                                                     │
                                         POST /exports/run
                                                     ▼
                                        Analytics DB (SQLite: analytics.db)
                                        resolved_invoices flat table
```

### Project structure

```
backend/
  app.py                        FastAPI application entry point
  config.py                     Environment-based configuration
  api/
    health.py                   GET /health
    invoices.py                 POST|GET /invoices, /resolve, /override, /seed
    exports.py                  POST /exports/run, GET /exports/summary
  db/
    connection.py               SQLAlchemy engine + session factory
  models/
    invoice.py                  SQLAlchemy ORM model
    schemas.py                  Pydantic request/response schemas
  services/
    invoice_processor.py        Normalisation layer (pure Python, no LLM)
    llm_agent.py                Claude agent with mandatory 3-tool loop
    export_service.py           Incremental export to analytics SQLite
    tools/
      historical_lookup.py      Tool 1: fuzzy search against historical_resolutions.json
      reference_validator.py    Tool 2: canonical lookup against reference_data.json
      compliance_checker.py     Tool 3: deterministic risk flag checker
data/
  new_post_ocr_inputs.json      15 seed invoices (OCR-extracted)
  historical_resolutions.json   51 previously resolved invoices (agent memory)
  reference_data.json           Canonical suppliers, categories, BU catalog, rules
  invoices.db                   Created on first run (operational)
  analytics.db                  Created on first export (analytical)
tests/
  conftest.py                   In-memory DB fixture
  test_invoice_processor.py     Unit tests for normalisation
  test_tools.py                 Unit tests for all three agent tools
  test_api.py                   Integration tests (no LLM needed)
scripts/
  seed.py                       CLI helper: seed + resolve + export
```

### Key design decisions

| Decision | Rationale |
|---|---|
| **Normalisation before LLM** | Dates, amounts, currency are 100% deterministic Python — no LLM tokens wasted |
| **Mandatory 3-tool order** | System prompt enforces `historical_lookup → reference_validator → compliance_checker`. Tool results are cached and passed forward (compliance checker receives history + reference context) |
| **Two SQLite files** | `invoices.db` = operational (full audit trail, raw + normalised + resolution). `analytics.db` = denormalised flat table ready for reporting/training |
| **Incremental export via `exported_at`** | Simple reliable watermark. Override resets `exported_at = NULL` for automatic re-export |
| **Idempotent import** | Duplicate `document_id` silently skipped in `/import` and `/seed` |
| **Tool call trace stored** | Every resolution includes `tool_calls_trace` array for full observability |

---

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Start the server

```bash
uvicorn backend.app:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

---

## Docker

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
```

---

## API reference

### Health

```bash
GET /health
```

### Ingest invoices

```bash
# Single invoice
curl -X POST http://localhost:8000/invoices \
  -H "Content-Type: application/json" \
  -d '{
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
    "field_confidence": {"supplier_name": 0.84, "supplier_tax_id": 0.35}
  }'

# Batch import (JSON array)
curl -X POST http://localhost:8000/invoices/import \
  -H "Content-Type: application/json" \
  -d '{"invoices": [...]}'

# Seed from data/new_post_ocr_inputs.json (no body needed)
curl -X POST http://localhost:8000/invoices/seed
```

### Query

```bash
# Single invoice (includes resolution if resolved)
curl http://localhost:8000/invoices/doc_new_001

# List with optional filter
curl "http://localhost:8000/invoices?status=pending&limit=20"
```

### Resolve (triggers LLM agent)

```bash
# ~5-20s — agent calls 3 tools then returns structured JSON
curl -X POST http://localhost:8000/invoices/doc_new_001/resolve

# Manual override / correction (resets export flag for re-export)
curl -X POST http://localhost:8000/invoices/doc_new_001/override \
  -H "Content-Type: application/json" \
  -d '{
    "canonical_supplier": "ORANGE ESPAGNE SA",
    "predicted_spend_category": "telecom",
    "predicted_business_unit": "it",
    "review_decision": "auto_approve",
    "confidence": 0.95,
    "decision_explanation": "Corrected by operator."
  }'
```

### Export to analytics layer

```bash
# Export all resolved-but-not-yet-exported → analytics.db
curl -X POST http://localhost:8000/exports/run

# Analytics summary
curl http://localhost:8000/exports/summary
```

---

## Full end-to-end walkthrough

```bash
# 1. Start server
uvicorn backend.app:app --reload --port 8000

# 2. Seed all 15 test invoices
curl -X POST http://localhost:8000/invoices/seed

# 3. Resolve one and inspect the tool call trace
curl -X POST http://localhost:8000/invoices/doc_new_001/resolve | python -m json.tool

# 4. Or use the convenience script to resolve all + export
python scripts/seed.py --resolve
```

### Expected resolution output (doc_new_001 — Orange Espana)

```json
{
  "canonical_supplier": "ORANGE ESPAGNE SA",
  "predicted_spend_category": "telecom",
  "predicted_business_unit": "it",
  "review_decision": "auto_approve",
  "confidence": 0.87,
  "decision_explanation": "Matched to ORANGE ESPAGNE SA via tax ID ESA82009812 in both
    the historical database (5 exact matches, all auto_approved as telecom/it) and the
    reference catalog. Compliance flags: missing tax_id flag (low confidence in OCR for
    that field) but historical and reference evidence is strong.",
  "tool_calls_trace": [
    {"tool": "lookup_historical_supplier", "input": {...}, "output": {"found": true, ...}},
    {"tool": "validate_against_reference",  "input": {...}, "output": {"found": true, ...}},
    {"tool": "check_compliance_flags",      "input": {...}, "output": {"risk_score": 0.2, ...}}
  ]
}
```

---

## Run tests

```bash
# All tests (no API key required — LLM resolve endpoint is not tested)
pytest tests/ -v

# Only normalisation layer
pytest tests/test_invoice_processor.py -v

# Only tool logic
pytest tests/test_tools.py -v

# API integration (uses in-memory SQLite)
pytest tests/test_api.py -v
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model ID |
| `OPERATIONAL_DB_URL` | `sqlite:///./data/invoices.db` | Operational database |
| `ANALYTICAL_DB_PATH` | `./data/analytics.db` | Analytics layer file |
| `HISTORICAL_DATA_PATH` | `./data/historical_resolutions.json` | Agent memory |
| `REFERENCE_DATA_PATH` | `./data/reference_data.json` | Canonical catalog |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `AUTO_APPROVE_THRESHOLD` | `0.75` | Used in README docs only; logic is in agent |

---

## Known limitations

1. **Synchronous LLM calls** — `/resolve` blocks until Claude responds (~5–20 s). Production would use async background tasks + polling or SSE.
2. **No authentication** — as per spec.
3. **SQLite concurrency** — fine for single-process; multi-worker deployment needs PostgreSQL.
4. **No bulk resolve endpoint** — use `scripts/seed.py --resolve` for batch testing.
5. **Static historical data** — loaded once at startup from JSON; production would query a live table.
6. **Confidence is agent-determined** — not a calibrated probability; formula is implicit in the system prompt logic.

## Possible future improvements

- Async resolution with `BackgroundTasks` + status polling
- PostgreSQL for operational DB + DuckDB / Parquet for analytics
- Embeddings-based semantic search on historical data instead of fuzzy string matching
- Re-injection of manually corrected resolutions as new historical records
- `POST /invoices/resolve-batch` endpoint
- Prompt caching for the (large) system prompt
- Confidence calibration based on historical accuracy metrics
- OpenAPI client generation for frontend or integration consumers

