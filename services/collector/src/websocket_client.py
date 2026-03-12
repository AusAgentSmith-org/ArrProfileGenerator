"""WebSocket client for predb.ovh real-time release feed."""

import asyncio
import json

import websockets

from profsync.config import settings
from profsync.logging import setup_logging
from profsync.queue import QUEUE_RAW_RELEASES, enqueue, get_redis

from src.categories import is_relevant_category

logger = setup_logging("collector.websocket")


class WebSocketCollector:
    def __init__(self) -> None:
        self.redis = get_redis()
        self.stats = {"received": 0, "enqueued": 0, "filtered": 0}

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Connect to predb.ovh WebSocket and process releases."""
        while not shutdown_event.is_set():
            try:
                await self._connect_and_listen(shutdown_event)
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception:
                logger.exception("WebSocket error, reconnecting in 10s...")
                await asyncio.sleep(10)

    async def _connect_and_listen(self, shutdown_event: asyncio.Event) -> None:
        logger.info("Connecting to %s", settings.predb_ws_url)
        async with websockets.connect(settings.predb_ws_url) as ws:
            logger.info("Connected to predb.ovh WebSocket")

            while not shutdown_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await ws.ping()
                    continue

                self._process_message(raw)

    def _process_message(self, raw: str) -> None:
        self.stats["received"] += 1

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from WebSocket: %s", raw[:200])
            return

        action = data.get("action", "")
        release = data.get("body", data)

        # We care about new releases and nuke events
        if action not in ("insert", "update", "nuke", "unnuke", "modnuke", ""):
            return

        category = release.get("cat", "")
        if not is_relevant_category(category):
            self.stats["filtered"] += 1
            return

        message = {
            "source": "websocket",
            "action": action or "insert",
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

        # Include nuke info if present
        nuke = release.get("nuke")
        if nuke:
            message["nuke"] = {
                "nuke_id": nuke.get("id"),
                "type": nuke.get("type", action),
                "reason": nuke.get("reason", ""),
                "network": nuke.get("net", ""),
                "nuked_at": nuke.get("nukeAt", ""),
            }

        enqueue(self.redis, QUEUE_RAW_RELEASES, message)
        self.stats["enqueued"] += 1

        if self.stats["enqueued"] % 100 == 0:
            logger.info(
                "Stats — received: %d, enqueued: %d, filtered: %d",
                self.stats["received"],
                self.stats["enqueued"],
                self.stats["filtered"],
            )
