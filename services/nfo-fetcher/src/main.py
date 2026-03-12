"""NFO Fetcher service — fetches NFOs from xREL, parses quality metrics."""

import signal
import threading
import time

from profsync.config import settings
from profsync.logging import setup_logging
from profsync.queue import QUEUE_NFO_NEEDED, dequeue, get_redis

from src.fetcher import fetch_and_parse_nfo

logger = setup_logging("nfo-fetcher")


def main() -> None:
    logger.info("Starting NFO fetcher service")

    if not settings.xrel_api_key:
        logger.warning(
            "No XREL_API_KEY configured — NFO fetching will be limited. "
            "Set XREL_API_KEY and XREL_API_SECRET in .env"
        )

    redis = get_redis()
    shutdown = threading.Event()

    def handle_signal(signum, frame):
        logger.info("Shutdown signal received")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    processed = 0
    fetched = 0
    errors = 0
    request_times: list[float] = []

    while not shutdown.is_set():
        message = dequeue(redis, QUEUE_NFO_NEEDED, timeout=5)
        if message is None:
            continue

        # Rate limiting for xREL API
        now = time.monotonic()
        request_times = [t for t in request_times if now - t < 60]
        if len(request_times) >= 10:  # conservative limit for xREL
            wait = 60 - (now - request_times[0])
            if wait > 0:
                logger.debug("Rate limit, waiting %.1fs", wait)
                time.sleep(wait)

        try:
            got_nfo = fetch_and_parse_nfo(message)
            processed += 1
            if got_nfo:
                fetched += 1
            request_times.append(time.monotonic())

            if processed % 50 == 0:
                logger.info(
                    "Processed %d — NFOs found: %d, errors: %d",
                    processed,
                    fetched,
                    errors,
                )
        except Exception:
            errors += 1
            logger.exception(
                "Error fetching NFO for release %s",
                message.get("release_name", "unknown"),
            )

    logger.info(
        "NFO fetcher shutdown — processed: %d, fetched: %d, errors: %d",
        processed,
        fetched,
        errors,
    )


if __name__ == "__main__":
    main()
