from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import backend.config as config

Path(config.DATA_DIR).mkdir(parents=True, exist_ok=True)

engine = sa.create_engine(
    config.OPERATIONAL_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend.models.invoice import Invoice  # noqa: F401
    Base.metadata.create_all(bind=engine)
