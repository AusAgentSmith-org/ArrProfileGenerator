"""REST client for predb.ovh historical backfill."""

import asyncio
import time

import aiohttp

from profsync.config import settings
from profsync.logging import setup_logging
from profsync.queue import QUEUE_RAW_RELEASES, enqueue, get_redis

from src.categories import is_relevant_category

logger = setup_logging("collector.backfill")


class BackfillClient:
    def __init__(self) -> None:
        self.redis = get_redis()
        self.base_url = settings.predb_api_url
        self.rate_limit = settings.predb_rate_limit
        self._request_times: list[float] = []

    async def run_initial_backfill(self, pages: int = 50) -> None:
        """Fetch recent releases via REST API for initial data seeding."""
        logger.info("Starting backfill — fetching %d pages", pages)
        total_enqueued = 0

        async with aiohttp.ClientSession() as session:
            for page in range(pages):
                await self._respect_rate_limit()

                try:
                    releases = await self._fetch_page(session, page)
                except Exception:
                    logger.exception("Backfill error on page %d", page)
                    continue

                if not releases:
                    logger.info("No more releases at page %d, backfill complete", page)
                    break

                page_enqueued = 0
                for release in releases:
                    category = release.get("cat", "")
                    if not is_relevant_category(category):
                        continue

                    message = {
                        "source": "backfill",
                        "action": "insert",
                        "release": {
                            "predb_id": release.get("id"),
                            "name": release.get("name", ""),
                            "team": release.get("team", ""),
                            "category": category,
                            "genre": release.get("genre", ""),
                            "url": release.get("url", ""),
                            "size_kb": release.get("size"),
                            "files": release.get("files"),
                            "pre_at": release.get("preAt", ""),
                        },
                    }

                    nuke = release.get("nuke")
                    if nuke:
                        message["nuke"] = {
                            "nuke_id": nuke.get("id"),
                            "type": nuke.get("type", "nuke"),
                            "reason": nuke.get("reason", ""),
                            "network": nuke.get("net", ""),
                            "nuked_at": nuke.get("nukeAt", ""),
                        }

                    enqueue(self.redis, QUEUE_RAW_RELEASES, message)
                    page_enqueued += 1

                total_enqueued += page_enqueued
                logger.info(
                    "Backfill page %d: %d releases enqueued (%d total)",
                    page,
                    page_enqueued,
                    total_enqueued,
                )

        logger.info("Backfill complete — %d releases enqueued", total_enqueued)

    async def _fetch_page(
        self, session: aiohttp.ClientSession, page: int, count: int = 100
    ) -> list[dict]:
        url = f"{self.base_url}/"
        params = {"count": count, "page": page}

        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        if data.get("status") != "success":
            logger.warning("API error: %s", data.get("message", "unknown"))
            return []

        return data.get("data", {}).get("rows", [])

    async def _respect_rate_limit(self) -> None:
        """Enforce predb.ovh rate limit: max N requests per 60 seconds."""
        now = time.monotonic()
        # Purge old timestamps
        self._request_times = [t for t in self._request_times if now - t < 60]

        if len(self._request_times) >= self.rate_limit:
            wait = 60 - (now - self._request_times[0])
            if wait > 0:
                logger.debug("Rate limit reached, waiting %.1fs", wait)
                await asyncio.sleep(wait)

        self._request_times.append(time.monotonic())
