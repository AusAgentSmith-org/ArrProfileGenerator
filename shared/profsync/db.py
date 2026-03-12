from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from profsync.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    return SessionLocal()
