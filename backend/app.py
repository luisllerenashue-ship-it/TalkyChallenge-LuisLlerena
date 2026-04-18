import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import backend.config as config
from backend.db.connection import init_db
from backend.api.health import router as health_router
from backend.api.invoices import router as invoices_router
from backend.api.exports import router as exports_router

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising operational database…")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Post-OCR Invoice Resolution Service",
    description=(
        "Receives structured post-OCR invoice payloads, normalises them, "
        "uses an LLM agent with internal tools to resolve business fields, "
        "and exports resolved records to an analytics layer."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(invoices_router)
app.include_router(exports_router)
