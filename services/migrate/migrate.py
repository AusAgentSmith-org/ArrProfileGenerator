"""Simple migration script — creates all tables from SQLAlchemy models."""

import logging
import sys
import time

from sqlalchemy import create_engine, text

from profsync.config import settings
from profsync.models import Base

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("migrate")


def wait_for_db(max_retries: int = 30, delay: float = 2.0) -> None:
    engine = create_engine(settings.database_url)
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database is ready")
            engine.dispose()
            return
        except Exception:
            logger.info(
                "Waiting for database (attempt %d/%d)...", attempt + 1, max_retries
            )
            time.sleep(delay)
    engine.dispose()
    logger.error("Database not available after %d attempts", max_retries)
    sys.exit(1)


def run_migrations() -> None:
    logger.info("Running migrations...")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    logger.info("All tables created successfully")


if __name__ == "__main__":
    wait_for_db()
    run_migrations()
