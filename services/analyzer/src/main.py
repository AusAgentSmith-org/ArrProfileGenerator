"""Analyzer service — periodic group profiling and tier computation."""

import signal
import threading
import time

from profsync.config import settings
from profsync.logging import setup_logging

from src.profiler import run_analysis

logger = setup_logging("analyzer")


def main() -> None:
    logger.info("Starting analyzer service (interval: %dm)", settings.analyzer_interval_minutes)
    shutdown = threading.Event()

    def handle_signal(signum, frame):
        logger.info("Shutdown signal received")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while not shutdown.is_set():
        try:
            logger.info("Running analysis cycle...")
            run_analysis()
            logger.info("Analysis cycle complete")
        except Exception:
            logger.exception("Error during analysis cycle")

        # Wait for next cycle or shutdown
        shutdown.wait(timeout=settings.analyzer_interval_minutes * 60)

    logger.info("Analyzer shutdown")


if __name__ == "__main__":
    main()
