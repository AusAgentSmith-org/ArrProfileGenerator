"""NFO Fetcher service — fetches NFOs from predb.net, parses quality metrics."""

import signal
import threading
import time

from profsync.logging import setup_logging
from profsync.queue import QUEUE_NFO_NEEDED, dequeue, get_redis

from src.fetcher import RateLimitError, fetch_and_parse_nfo

logger = setup_logging("nfo-fetcher")

# Minimum seconds between requests to predb.net NFO endpoint
# Each fetch = 2 HTTP requests (lookup + download)
REQUEST_INTERVAL = 5


def main() -> None:
    logger.info("Starting NFO fetcher service (predb.net, interval: %ds)", REQUEST_INTERVAL)

    redis = get_redis()
    shutdown = threading.Event()

    def handle_signal(signum, frame):
        logger.info("Shutdown signal received")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    processed = 0
    fetched = 0
    not_found = 0
    errors = 0
    backoff = REQUEST_INTERVAL

    while not shutdown.is_set():
        message = dequeue(redis, QUEUE_NFO_NEEDED, timeout=5)
        if message is None:
            continue

        # Pace requests
        time.sleep(backoff)

        try:
            got_nfo = fetch_and_parse_nfo(message)
            processed += 1
            if got_nfo:
                fetched += 1
                logger.info("NFO found: %s", message.get("release_name", "?"))
            else:
                not_found += 1

            # Reset backoff on success
            backoff = REQUEST_INTERVAL

            if processed % 50 == 0:
                logger.info(
                    "Progress — processed: %d, found: %d, not found: %d, errors: %d",
                    processed,
                    fetched,
                    not_found,
                    errors,
                )
        except RateLimitError:
            backoff = min(backoff * 2, 120)
            logger.warning("Rate limited — backing off to %ds", backoff)
            # Re-enqueue the message so we don't lose it
            from profsync.queue import enqueue, QUEUE_NFO_NEEDED as q
            enqueue(redis, q, message)
        except Exception:
            errors += 1
            logger.exception(
                "Error fetching NFO for release %s",
                message.get("release_name", "unknown"),
            )

    logger.info(
        "NFO fetcher shutdown — processed: %d, fetched: %d, not found: %d, errors: %d",
        processed,
        fetched,
        not_found,
        errors,
    )


if __name__ == "__main__":
    main()
