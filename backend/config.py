import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

OPERATIONAL_DB_URL: str = os.getenv(
    "OPERATIONAL_DB_URL",
    f"sqlite:///{DATA_DIR.as_posix()}/invoices.db",
)
ANALYTICAL_DB_PATH: str = os.getenv(
    "ANALYTICAL_DB_PATH",
    str(DATA_DIR / "analytics.db"),
)
HISTORICAL_DATA_PATH: str = os.getenv(
    "HISTORICAL_DATA_PATH",
    str(DATA_DIR / "historical_resolutions.json"),
)
REFERENCE_DATA_PATH: str = os.getenv(
    "REFERENCE_DATA_PATH",
    str(DATA_DIR / "reference_data.json"),
)

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
AUTO_APPROVE_THRESHOLD: float = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.75"))
