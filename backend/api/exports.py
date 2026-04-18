from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.connection import get_db
from backend.services.export_service import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])

_svc: ExportService | None = None


def _get_svc() -> ExportService:
    global _svc
    if _svc is None:
        _svc = ExportService()
    return _svc


@router.post("/run")
def run_export(db: Session = Depends(get_db)):
    """
    Incrementally export all resolved-but-not-yet-exported invoices
    to the analytics layer (analytics.db).
    """
    count = _get_svc().export_pending(db)
    return {
        "exported_count": count,
        "export_timestamp": datetime.utcnow().isoformat() + "Z",
        "message": f"Exported {count} invoice(s) to the analytics layer.",
    }


@router.get("/summary")
def export_summary():
    """Return aggregate statistics from the analytics layer."""
    return _get_svc().get_summary()
