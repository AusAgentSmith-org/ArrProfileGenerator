import json
import logging

import redis

from profsync.config import settings

logger = logging.getLogger(__name__)

QUEUE_RAW_RELEASES = "profsync:queue:raw_releases"
QUEUE_NFO_NEEDED = "profsync:queue:nfo_needed"


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def enqueue(client: redis.Redis, queue: str, data: dict) -> None:
    client.lpush(queue, json.dumps(data))


def dequeue(client: redis.Redis, queue: str, timeout: int = 5) -> dict | None:
    """Blocking pop from a Redis list. Returns parsed dict or None on timeout."""
    result = client.brpop(queue, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)


def queue_length(client: redis.Redis, queue: str) -> int:
    return client.llen(queue)
