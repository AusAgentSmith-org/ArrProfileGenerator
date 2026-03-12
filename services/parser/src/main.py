"""Parser service — consumes raw releases, parses with guessit, stores to DB."""

import signal
import threading

from profsync.logging import setup_logging
from profsync.queue import QUEUE_RAW_RELEASES, dequeue, get_redis

from src.processor import process_release

logger = setup_logging("parser")


def main() -> None:
    logger.info("Starting parser service")
    redis = get_redis()
    shutdown = threading.Event()

    def handle_signal(signum, frame):
        logger.info("Shutdown signal received")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    processed = 0
    errors = 0

    while not shutdown.is_set():
        message = dequeue(redis, QUEUE_RAW_RELEASES, timeout=5)
        if message is None:
            continue

        try:
            process_release(message)
            processed += 1
            if processed % 100 == 0:
                logger.info("Processed %d releases (%d errors)", processed, errors)
        except Exception:
            errors += 1
            logger.exception(
                "Error processing release: %s",
                message.get("release", {}).get("name", "unknown"),
            )

    logger.info(
        "Parser shutdown — processed: %d, errors: %d", processed, errors
    )


if __name__ == "__main__":
    main()
