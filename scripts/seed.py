"""
Quick seed script: imports all invoices from data/new_post_ocr_inputs.json
via the running API, then optionally resolves them all.

Usage:
    python scripts/seed.py                # import only
    python scripts/seed.py --resolve      # import + resolve all
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = "http://localhost:8000"


def seed(resolve: bool = False) -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=120.0)

    print("Seeding invoices from data/new_post_ocr_inputs.json …")
    resp = client.post("/invoices/seed")
    resp.raise_for_status()
    body = resp.json()
    print(
        f"  created={body['created']}  skipped={body['skipped']}  errors={body['errors']}"
    )

    if not resolve:
        print("Done. To resolve, re-run with --resolve")
        return

    print("\nResolving all pending invoices …")
    list_resp = client.get("/invoices?status=pending&limit=100")
    list_resp.raise_for_status()
    pending = list_resp.json()["items"]

    for inv in pending:
        inv_id = inv["id"]
        print(f"  Resolving {inv_id} … ", end="", flush=True)
        try:
            r = client.post(f"/invoices/{inv_id}/resolve")
            resolution = r.json().get("resolution") or {}
            decision = resolution.get("review_decision", "?")
            confidence = resolution.get("confidence", 0.0)
            print(f"{decision}  (confidence={confidence:.2f})")
        except Exception as exc:
            print(f"ERROR: {exc}")
        time.sleep(0.5)

    print("\nRunning incremental export to analytics layer …")
    exp = client.post("/exports/run")
    exp.raise_for_status()
    print(f"  {exp.json()['message']}")

    print("\nAnalytics summary:")
    summary = client.get("/exports/summary").json()
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolve", action="store_true", help="Also resolve all invoices")
    args = parser.parse_args()
    seed(resolve=args.resolve)
