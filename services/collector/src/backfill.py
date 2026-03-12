"""REST client for api.predb.net historical backfill."""

import asyncio
import time
from datetime import datetime, timezone

import aiohttp

from profsync.config import settings
from profsync.logging import setup_logging
from profsync.queue import QUEUE_RAW_RELEASES, enqueue, get_redis

from src.categories import is_relevant_category

logger = setup_logging("collector.backfill")

# Sections to backfill — 100 pages × 20 per page = 2000 releases each
BACKFILL_SECTIONS = [
    "TV-WEB-HD-X264",
    "TV-WEB-HD-X265",
    "X264",
    "X265",
    "BLURAY",
    "UHD",
    "DVDR",
    "XVID",
    "TV-BLURAY",
    "TV-SD",
    "TV-XVID",
    "TV-UHD",
    "TV-X264",
    "TV-X265",
]


class BackfillClient:
    def __init__(self) -> None:
        self.redis = get_redis()
        self.base_url = settings.predb_api_url
        self.rate_limit = settings.predb_rate_limit
        self._request_times: list[float] = []

    async def run_initial_backfill(self) -> None:
        """Fetch recent releases per section for initial data seeding."""
        logger.info("Starting backfill across %d sections", len(BACKFILL_SECTIONS))
        grand_total = 0

        async with aiohttp.ClientSession() as session:
            for section in BACKFILL_SECTIONS:
                total = await self._backfill_section(session, section)
                grand_total += total
                logger.info("Section %s complete — %d releases enqueued", section, total)

        logger.info("Backfill complete — %d releases enqueued total", grand_total)

    async def _backfill_section(
        self, session: aiohttp.ClientSession, section: str, pages: int = 100
    ) -> int:
        total_enqueued = 0

        for page in range(1, pages + 1):
            await self._respect_rate_limit()

            try:
                releases = await self._fetch_page(session, page, section)
            except Exception:
                logger.exception("Backfill error on %s page %d", section, page)
                continue

            if not releases:
                logger.info("No more releases for %s at page %d", section, page)
                break

            page_enqueued = 0
            for release in releases:
                category = release.get("section", "")
                if not is_relevant_category(category):
                    continue

                pretime = release.get("pretime", 0)
                pre_at = datetime.fromtimestamp(pretime, tz=timezone.utc).isoformat() if pretime else ""

                message = {
                    "source": "backfill",
                    "action": "insert",
                    "release": {
                        "predb_id": release.get("id"),
                        "name": release.get("release", ""),
                        "team": release.get("group", ""),
                        "category": category,
                        "genre": release.get("genre", ""),
                        "url": release.get("url", ""),
                        "size_kb": release.get("size"),
                        "files": release.get("files"),
                        "pre_at": pre_at,
                    },
                }

                status = release.get("status", 0)
                if status != 0:
                    message["nuke"] = {
                        "nuke_id": None,
                        "type": "nuke" if status == 1 else "unnuke",
                        "reason": release.get("reason", ""),
                        "network": "",
                        "nuked_at": pre_at,
                    }

                enqueue(self.redis, QUEUE_RAW_RELEASES, message)
                page_enqueued += 1

            total_enqueued += page_enqueued

        return total_enqueued

    async def _fetch_page(
        self, session: aiohttp.ClientSession, page: int, section: str
    ) -> list[dict]:
        url = f"{self.base_url}/"
        params = {"page": page, "section": section}

        for attempt in range(5):
            async with session.get(url, params=params) as resp:
                if resp.status == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning("Rate limited on %s page %d, waiting %ds", section, page, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = await resp.json()
                break
        else:
            logger.error("Failed to fetch %s page %d after retries", section, page)
            return []

        if data.get("status") != "success":
            logger.warning("API error: %s", data.get("message", "unknown"))
            return []

        return data.get("data", [])

    async def _respect_rate_limit(self) -> None:
        """Enforce rate limit: max N requests per 60 seconds."""
        now = time.monotonic()
        self._request_times = [t for t in self._request_times if now - t < 60]

        if len(self._request_times) >= self.rate_limit:
            wait = 60 - (now - self._request_times[0])
            if wait > 0:
                logger.debug("Rate limit reached, waiting %.1fs", wait)
                await asyncio.sleep(wait)

        self._request_times.append(time.monotonic())
