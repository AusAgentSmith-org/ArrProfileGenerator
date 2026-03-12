"""Polling client for api.predb.net real-time release feed."""

import asyncio
from datetime import datetime, timezone

import aiohttp

from profsync.config import settings
from profsync.logging import setup_logging
from profsync.queue import QUEUE_RAW_RELEASES, enqueue, get_redis

from src.categories import is_relevant_category

logger = setup_logging("collector.poller")

REDIS_KEY_LAST_ID = "collector:last_predb_id"
POLL_INTERVAL = 30  # seconds


class WebSocketCollector:
    """Polls api.predb.net every 30s for new releases."""

    def __init__(self) -> None:
        self.redis = get_redis()
        self.base_url = settings.predb_api_url
        self.stats = {"received": 0, "enqueued": 0, "filtered": 0}

    async def run(self, shutdown_event: asyncio.Event) -> None:
        logger.info("Starting poller (interval: %ds)", POLL_INTERVAL)
        while not shutdown_event.is_set():
            try:
                await self._poll()
            except Exception:
                logger.exception("Poll error")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def _poll(self) -> None:
        last_id = int(self.redis.get(REDIS_KEY_LAST_ID) or 0)

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/", params={"page": 1}) as resp:
                resp.raise_for_status()
                data = await resp.json()

        releases = data.get("data", [])
        self.stats["received"] += len(releases)

        new_releases = [r for r in releases if r.get("id", 0) > last_id]
        if not new_releases:
            return

        new_max_id = max(r["id"] for r in new_releases)

        for release in new_releases:
            category = release.get("section", "")
            if not is_relevant_category(category):
                self.stats["filtered"] += 1
                continue

            pretime = release.get("pretime", 0)
            pre_at = datetime.fromtimestamp(pretime, tz=timezone.utc).isoformat() if pretime else ""

            message = {
                "source": "poll",
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
            self.stats["enqueued"] += 1

        self.redis.set(REDIS_KEY_LAST_ID, new_max_id)

        logger.info(
            "Poll: %d new releases enqueued (last_id: %d → %d)",
            len(new_releases),
            last_id,
            new_max_id,
        )

        if self.stats["enqueued"] % 100 == 0 and self.stats["enqueued"] > 0:
            logger.info(
                "Stats — received: %d, enqueued: %d, filtered: %d",
                self.stats["received"],
                self.stats["enqueued"],
                self.stats["filtered"],
            )
