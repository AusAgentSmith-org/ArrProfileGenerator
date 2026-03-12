"""Collector service — ingests releases from predb.ovh via WebSocket and REST."""

import asyncio
import signal

from profsync.logging import setup_logging

from src.websocket_client import WebSocketCollector
from src.backfill import BackfillClient

logger = setup_logging("collector")


async def main() -> None:
    logger.info("Starting collector service")

    ws_collector = WebSocketCollector()
    backfill = BackfillClient()

    shutdown_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    # Run initial backfill then switch to websocket for live updates
    try:
        await backfill.run_initial_backfill()
        await ws_collector.run(shutdown_event)
    except asyncio.CancelledError:
        logger.info("Collector cancelled")
    finally:
        logger.info("Collector shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
