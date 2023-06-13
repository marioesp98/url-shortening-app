from typing import Optional

import redis
import structlog
from redis.client import Redis

from .settings import settings

log = structlog.get_logger("url-shortening-app.redis")


class RedisClient:
    client: Optional[Redis] = None


# Create a singleton instance of RedisClient. This will be used to store the Redis client connection across requests.
_rdb = RedisClient()


def connect_to_redis() -> Redis:
    """
    Connect to Redis.
    """
    log.info("Connecting to Redis...")
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password,
        db=settings.redis_db,
        decode_responses=True,
    )


def get_redis() -> Redis:
    """
    Get or create connection to Redis.
    """
    if _rdb.client is None:
        _rdb.client = connect_to_redis()
    return _rdb.client
