"""Import TRaSH Guides tier data as a read-only benchmark layer."""

import logging
import re
import sys
import time
from datetime import datetime

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from profsync.config import settings
from profsync.models import Base, TrashGroupTier

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("trash-importer")

RADARR_BASE = (
    "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/radarr/cf"
)
SONARR_BASE = (
    "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/sonarr/cf"
)

# filename slug -> (category, tier_number)
TIER_FILES = {
    "hd-bluray-tier-01": ("hd-bluray", 1),
    "hd-bluray-tier-02": ("hd-bluray", 2),
    "hd-bluray-tier-03": ("hd-bluray", 3),
    "uhd-bluray-tier-01": ("uhd-bluray", 1),
    "uhd-bluray-tier-02": ("uhd-bluray", 2),
    "uhd-bluray-tier-03": ("uhd-bluray", 3),
    "web-tier-01": ("web", 1),
    "web-tier-02": ("web", 2),
    "web-tier-03": ("web", 3),
    "remux-tier-01": ("remux", 1),
    "remux-tier-02": ("remux", 2),
    "remux-tier-03": ("remux", 3),
    "lq": ("lq", 0),
}


def fetch_json(url: str, retries: int = 3) -> dict | None:
    """Fetch JSON from URL with simple retry."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 404:
                logger.warning("Not found: %s", url)
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Attempt %d failed for %s: %s", attempt + 1, url, e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def extract_groups(data: dict) -> list[str]:
    """Extract group names from TRaSH CF JSON specifications."""
    groups = []
    for spec in data.get("specifications", []):
        if spec.get("implementation") != "ReleaseGroupSpecification":
            continue
        fields = spec.get("fields", {})
        value = fields.get("value", "")
        if not value:
            continue
        # Strip regex anchors
        cleaned = value.strip("^$")
        # Extract names from parenthesized groups, or use the whole string
        paren_groups = re.findall(r"\(([^)]+)\)", cleaned)
        if paren_groups:
            for group in paren_groups:
                # Handle alternation within parens
                groups.extend(group.split("|"))
        else:
            # No parens — handle alternation at top level
            groups.extend(cleaned.split("|"))
    # Clean up: strip whitespace, remove empty strings
    return [g.strip() for g in groups if g.strip()]


def import_tier_file(
    session: Session,
    slug: str,
    category: str,
    tier_number: int,
    base_url: str,
    app_label: str,
) -> int:
    """Import a single TRaSH tier file. Returns number of groups upserted."""
    url = f"{base_url}/{slug}.json"
    data = fetch_json(url)
    if data is None:
        return 0

    tier_name = data.get("name", slug)
    trash_score = data.get("trash_scores", {}).get("default")
    groups = extract_groups(data)

    count = 0
    for group_name in groups:
        # Check if this group already exists for this tier+app
        existing = (
            session.query(TrashGroupTier)
            .filter_by(
                group_name=group_name,
                trash_tier_name=tier_name,
                app_type=app_label,
            )
            .first()
        )
        if existing:
            existing.trash_tier_category = category
            existing.trash_tier_number = tier_number
            existing.trash_score = trash_score
            existing.imported_at = datetime.utcnow()
        else:
            session.add(
                TrashGroupTier(
                    group_name=group_name,
                    trash_tier_name=tier_name,
                    trash_tier_category=category,
                    trash_tier_number=tier_number,
                    app_type=app_label,
                    trash_score=trash_score,
                    imported_at=datetime.utcnow(),
                )
            )
        count += 1

    session.commit()
    return count


def deduplicate_both(session: Session) -> int:
    """Mark groups that appear in both radarr and sonarr as 'both'."""
    # Find group+tier combos that exist in both radarr and sonarr
    radarr_keys = set()
    sonarr_keys = set()
    for row in session.query(TrashGroupTier).all():
        key = (row.group_name, row.trash_tier_name)
        if row.app_type == "radarr":
            radarr_keys.add(key)
        elif row.app_type == "sonarr":
            sonarr_keys.add(key)

    both_keys = radarr_keys & sonarr_keys
    if not both_keys:
        return 0

    count = 0
    for group_name, tier_name in both_keys:
        # Update radarr row to "both", delete sonarr duplicate
        radarr_row = (
            session.query(TrashGroupTier)
            .filter_by(group_name=group_name, trash_tier_name=tier_name, app_type="radarr")
            .first()
        )
        sonarr_row = (
            session.query(TrashGroupTier)
            .filter_by(group_name=group_name, trash_tier_name=tier_name, app_type="sonarr")
            .first()
        )
        if radarr_row and sonarr_row:
            radarr_row.app_type = "both"
            session.delete(sonarr_row)
            count += 1

    session.commit()
    return count


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
            logger.info("Waiting for database (attempt %d/%d)...", attempt + 1, max_retries)
            time.sleep(delay)
    engine.dispose()
    logger.error("Database not available after %d attempts", max_retries)
    sys.exit(1)


def main() -> None:
    wait_for_db()

    engine = create_engine(settings.database_url)
    # Ensure table exists
    Base.metadata.create_all(engine)

    total = 0
    with Session(engine) as session:
        for slug, (category, tier_number) in TIER_FILES.items():
            for base_url, app_label in [(RADARR_BASE, "radarr"), (SONARR_BASE, "sonarr")]:
                count = import_tier_file(session, slug, category, tier_number, base_url, app_label)
                if count:
                    logger.info(
                        "Imported %d groups from %s/%s.json", count, app_label, slug
                    )
                total += count

        deduped = deduplicate_both(session)
        if deduped:
            logger.info("Deduplicated %d groups appearing in both radarr and sonarr", deduped)

    engine.dispose()
    logger.info("Import complete: %d total group-tier entries processed", total)


if __name__ == "__main__":
    main()
