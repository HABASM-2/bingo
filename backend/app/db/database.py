from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


Base = declarative_base()

from typing import Generator


def get_db() -> Generator:

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()