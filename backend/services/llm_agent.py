"""
LLM Agent — uses Anthropic Claude with tool calling.

Flow (enforced by system prompt):
  1. lookup_historical_supplier  — mandatory first call
  2. validate_against_reference  — mandatory second call
  3. check_compliance_flags      — mandatory third call (receives cached results from 1 & 2)
  4. Final structured JSON response

The agent resolves:
  canonical_supplier, predicted_spend_category, predicted_business_unit,
  review_decision, confidence, decision_explanation
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import anthropic

import backend.config as config
from backend.services.tools.historical_lookup import HistoricalLookup
from backend.services.tools.reference_validator import ReferenceValidator
from backend.services.tools.compliance_checker import ComplianceChecker

logger = logging.getLogger(__name__)

# ── Tool definitions (JSON Schema) ────────────────────────────────────────────

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "lookup_historical_supplier",
        "description": (
            "Search the historical resolved-invoices database for this supplier. "
            "Returns canonical name, typical spend category, typical business unit, "
            "recent review decisions, and average confidence from past resolutions. "
            "Call this FIRST before any other tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tax_id": {
                    "type": "string",
                    "description": "Supplier VAT/tax ID. Pass empty string if missing.",
                },
                "supplier_name": {
                    "type": "string",
                    "description": "Supplier name as extracted by OCR (may contain typos).",
                },
            },
            "required": ["supplier_name"],
        },
    },
    {
        "name": "validate_against_reference",
        "description": (
            "Look up the supplier in the canonical reference catalog. "
            "Returns official canonical name, known aliases, typical category, "
            "typical business unit, and the full list of valid categories/BUs. "
            "Call this SECOND, after lookup_historical_supplier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tax_id": {
                    "type": "string",
                    "description": "Supplier VAT/tax ID. Pass empty string if missing.",
                },
                "supplier_name": {
                    "type": "string",
                    "description": "Supplier name from the invoice.",
                },
            },
            "required": ["supplier_name"],
        },
    },
    {
        "name": "check_compliance_flags",
        "description": (
            "Run deterministic compliance checks on the invoice. "
            "Returns risk flags (missing tax ID, low OCR confidence, unknown supplier, "
            "conflicting history) and an overall risk_score [0-1]. "
            "Call this THIRD, after the two lookup tools. "
            "Use the flags and risk_score to decide review_decision and confidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "supplier_tax_id": {
                    "type": "string",
                    "description": "Supplier tax ID or empty string.",
                },
                "supplier_name": {
                    "type": "string",
                    "description": "Supplier name from invoice.",
                },
                "field_confidence": {
                    "type": "object",
                    "description": (
                        "OCR confidence per field, e.g. "
                        '{"supplier_name": 0.84, "description": 0.90}'
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Invoice description text.",
                },
            },
            "required": ["supplier_name"],
        },
    },
]

SYSTEM_PROMPT = """You are an intelligent invoice resolution agent for a corporate finance system.

Your task is to analyze post-OCR invoice data and resolve six business fields:
  - canonical_supplier       : Official canonical supplier name (e.g. "ORANGE ESPAGNE SA")
  - predicted_spend_category : One of: telecom, software, travel, office_supplies,
                               professional_services, utilities, other
  - predicted_business_unit  : One of: operations, sales, marketing, it, general_admin
  - review_decision          : "auto_approve" or "needs_review"
  - confidence               : Float 0.0–1.0
  - decision_explanation     : Brief human-readable explanation

MANDATORY TOOL USAGE — you MUST call ALL three tools in this order before responding:
  1. lookup_historical_supplier  (check if we have seen this supplier before)
  2. validate_against_reference  (confirm canonical name and valid values)
  3. check_compliance_flags      (assess risk and review need)

DECISION LOGIC:
  - Strong tax_id match in history + reference → high confidence, lean auto_approve
  - Name fuzzy match only, no tax_id → reduce confidence by ~0.15
  - Unknown supplier (not in history AND not in reference) → needs_review
  - has_high_severity flag → needs_review unless other signals are very strong
  - risk_score > 0.40 → needs_review
  - risk_score ≤ 0.25 AND strong history match → auto_approve

WHAT NOT TO DO:
  - Do NOT parse dates, convert numbers, or validate JSON (that is done before you run)
  - Do NOT invent canonical names — use what the tools return
  - Do NOT use categories or business units outside the valid_categories/valid_business_units lists

RESPONSE FORMAT:
After using all three tools, respond with ONLY a valid JSON object:
{
  "canonical_supplier": "...",
  "predicted_spend_category": "...",
  "predicted_business_unit": "...",
  "review_decision": "auto_approve" | "needs_review",
  "confidence": 0.XX,
  "decision_explanation": "..."
}
No markdown, no explanation outside the JSON.
"""


class InvoiceAgent:
    def __init__(self) -> None:
        if not config.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Create a .env file from .env.example and add your key."
            )
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.historical_lookup = HistoricalLookup(config.HISTORICAL_DATA_PATH)
        self.reference_validator = ReferenceValidator(config.REFERENCE_DATA_PATH)
        self.compliance_checker = ComplianceChecker()

    # ── tool execution ────────────────────────────────────────────────────────

    def _run_tool(
        self,
        name: str,
        tool_input: Dict[str, Any],
        invoice_ctx: Dict[str, Any],
        cache: Dict[str, Any],
    ) -> str:
        try:
            if name == "lookup_historical_supplier":
                result = self.historical_lookup.get_supplier_history(
                    tax_id=tool_input.get("tax_id") or invoice_ctx.get("supplier_tax_id"),
                    supplier_name=tool_input.get("supplier_name") or invoice_ctx.get("supplier_name"),
                )

            elif name == "validate_against_reference":
                result = self.reference_validator.get_supplier_info(
                    tax_id=tool_input.get("tax_id") or invoice_ctx.get("supplier_tax_id"),
                    supplier_name=tool_input.get("supplier_name") or invoice_ctx.get("supplier_name"),
                )

            elif name == "check_compliance_flags":
                result = self.compliance_checker.check(
                    supplier_tax_id=(
                        tool_input.get("supplier_tax_id")
                        or invoice_ctx.get("supplier_tax_id")
                    ),
                    supplier_name=(
                        tool_input.get("supplier_name")
                        or invoice_ctx.get("supplier_name", "")
                    ),
                    field_confidence=(
                        tool_input.get("field_confidence")
                        or invoice_ctx.get("field_confidence")
                    ),
                    description=(
                        tool_input.get("description")
                        or invoice_ctx.get("description")
                    ),
                    # Enrich with results from previous tool calls
                    historical_data=cache.get("lookup_historical_supplier"),
                    reference_data=cache.get("validate_against_reference"),
                )
            else:
                result = {"error": f"Unknown tool: {name}"}

        except Exception as exc:
            logger.error("Tool %s raised: %s", name, exc)
            result = {"error": str(exc)}

        return json.dumps(result, ensure_ascii=False, default=str)

    # ── main resolution loop ──────────────────────────────────────────────────

    def resolve(self, normalized_invoice: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the agentic tool-use loop and return the resolution dict.
        The dict includes tool_calls_trace for observability.
        """
        # Build user message (exclude raw_ocr_text to keep context concise)
        invoice_summary = {
            k: v for k, v in normalized_invoice.items()
            if k not in ("raw_ocr_text",) and v is not None
        }

        user_msg = (
            "Please resolve this invoice using the required tools:\n\n"
            + json.dumps(invoice_summary, indent=2, ensure_ascii=False)
        )

        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_msg}]
        tool_calls_trace: List[Dict[str, Any]] = []
        tool_cache: Dict[str, Any] = {}

        for iteration in range(8):
            logger.info(
                "Agent iteration %d for %s",
                iteration + 1,
                normalized_invoice.get("document_id"),
            )

            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                # Extract final JSON
                full_text = "".join(
                    b.text for b in response.content if hasattr(b, "text")
                )
                resolution = self._parse_json_response(full_text)
                resolution["tool_calls_trace"] = tool_calls_trace
                return resolution

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    logger.info("Calling tool: %s  input: %s", block.name, block.input)
                    result_str = self._run_tool(
                        block.name, block.input, normalized_invoice, tool_cache
                    )
                    result_data = json.loads(result_str)

                    # Cache tool result so later tools can reference it
                    tool_cache[block.name] = result_data

                    tool_calls_trace.append({
                        "tool": block.name,
                        "input": block.input,
                        "output": result_data,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

                messages.append({"role": "user", "content": tool_results})
            else:
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                break

        logger.error("Agent loop exhausted for %s", normalized_invoice.get("document_id"))
        return self._fallback(normalized_invoice, tool_calls_trace)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        import re

        # Strip markdown code fences if present
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            json_str = m.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end] if start != -1 and end > start else text

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.error("Could not parse agent JSON: %.200s", text)
            return self._fallback({}, [])

        required_fields = {
            "canonical_supplier": "UNKNOWN",
            "predicted_spend_category": "other",
            "predicted_business_unit": "general_admin",
            "review_decision": "needs_review",
            "confidence": 0.3,
            "decision_explanation": "Agent response could not be fully parsed.",
        }
        for field, default in required_fields.items():
            if field not in data:
                data[field] = default

        # Clamp confidence
        data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.3))))
        return data

    def _fallback(
        self,
        invoice: Dict[str, Any],
        trace: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "canonical_supplier": invoice.get("supplier_name") or "UNKNOWN",
            "predicted_spend_category": "other",
            "predicted_business_unit": "general_admin",
            "review_decision": "needs_review",
            "confidence": 0.10,
            "decision_explanation": (
                "Agent resolution failed or timed out. Manual review required."
            ),
            "tool_calls_trace": trace,
        }
