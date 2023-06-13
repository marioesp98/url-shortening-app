import datetime
import hashlib
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import redis
import sentry_sdk
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl
from redis.client import Redis
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_409_CONFLICT,
    HTTP_429_TOO_MANY_REQUESTS,
)

from .rdb import get_redis
from .settings import settings

log = structlog.get_logger("url-shortening-app.main")

if settings.sentry_dsn:
    opts = {
        "traces_sample_rate": settings.sentry_traces_sample_rate,
        "profiles_sample_rate": settings.sentry_profiles_sample_rate,
    }
    log.info("Initializing Sentry SDK and integrations...", **opts)
    sentry_sdk.init(dsn=settings.sentry_dsn, **opts)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Context manager to initialize and close resources for the application.
    """
    # Initialize Redis connection.
    rdb = get_redis()
    try:
        rdb.ping()
    except redis.ConnectionError as e:
        log.error("Error connecting to Redis", exc_info=e)
        raise e
    # Run the rest of the application.
    yield
    # Close Redis connection.
    rdb.close()


app = FastAPI(
    title="URL Shortening Service",
    description="A simple URL shortening service",
    version="0.1.0",
    lifespan=lifespan,
)


def get_api_key(request: Request, x_api_key: str = Header(), rdb: Redis = Depends(get_redis)) -> str:
    """
    Get the API key from the request headers.
    """
    key = f"api-key:{x_api_key}"
    if rdb.get(key):
        return x_api_key
    log.debug("Invalid API key", key=key, x_api_key=x_api_key, path=request.url.path)
    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_rate_limit(request: Request, rdb: Redis = Depends(get_redis), api_key: str = Depends(get_api_key)) -> None:
    """
    Rate limit the number of requests per API key and endpoint.
    """
    limit = 10  # Number of requests allowed per period.
    period_in_seconds = 60  # Period window in seconds.
    key = f"rate-limit:{api_key}:{request.url.path}"
    if rdb.setnx(key, limit):
        log.debug("Rate limit set", key=key, limit=limit, period_in_seconds=period_in_seconds)
        rdb.expire(key, period_in_seconds)
    val = rdb.get(key)
    if val and int(val) > 0:
        rdb.decrby(key, 1)
    else:
        log.debug("Rate limit exceeded", key=key, limit=limit, period_in_seconds=period_in_seconds)
        raise HTTPException(status_code=HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")


class ApiKey(BaseModel):
    api_key: str
    expires_at: Optional[datetime.datetime] = None
    issued_at: datetime.datetime


@app.post("/api/v1/issue/api_key", response_model=ApiKey)
def issue(expires_in_seconds: Optional[int] = 3600, rdb: Redis = Depends(get_redis)):
    """
    Issue a new API key for the user.

    :param expires_in_seconds: Time to live for the API key in seconds.
    :return: API key.
    """
    api_key = uuid.uuid4().hex
    key = f"api-key:{api_key}"
    rdb.set(key, 1)
    if expires_in_seconds:
        rdb.expire(key, expires_in_seconds)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in_seconds)
    else:
        expires_at = None
    return {"api_key": api_key, "expires_at": expires_at, "issued_at": datetime.datetime.utcnow()}


class ShortenRequest(BaseModel):
    url: HttpUrl
    ttl: Optional[int] = None  # Time to live in seconds. Default no expiration.


@app.post("/api/v1/shorten", dependencies=[Depends(get_rate_limit)])
def shorten(payload: ShortenRequest, rdb: Redis = Depends(get_redis)):
    """
    Given a URL, returns a shortened URL. This endpoint is protected by an API key and can be accessed only by
    authorized users.

    :param payload: URL to be shortened.
    :return: Shortened URL.
    """
    # We could rely on some hashing algorithm to generate the digest. For example, md5 or sha256.
    # And then we could truncate the digest to a fixed length to generate a shortened version (though this
    # increases the chances of hash collision):
    digest = hashlib.md5(payload.url.encode("UTF-8")).hexdigest()
    digest = digest[:10]

    # We do this instead of using a random string generator because we want to be able to reuse the same digest
    # for the same URL. This way, we can avoid storing the same URL multiple times.

    key = f"digest:{digest}"
    url = rdb.get(key)
    if not url:
        # If the key does not exist, then we can safely set it.
        rdb.set(key, payload.url)
        # Set the time to live if specified. This is useful for expiring URLs in free tier plans.
        if payload.ttl:
            rdb.expire(key, payload.ttl)
    else:
        # If the key exists  and the URL is different, then we have a hash collision.
        # TODO: We could just add 1 to the digest and try again until we find a digest that is not in use.
        log.warning("Hash collision detected", digest=digest, payload_url=payload.url, url=url)
        if url != payload.url:
            raise HTTPException(status_code=HTTP_409_CONFLICT, detail="The URL cannot be shortened")

    return f"/r/{digest}"


@app.get("/r/{digest}")
def redirect(
    digest: str, referrer: Optional[str] = None, campaign: Optional[str] = None, rdb: Redis = Depends(get_redis)
):
    """
    Redirect to the original URL given the shortened URL.

    :param digest: The shortened URL.
    :param referrer: Source of the request. Default None.
    :param campaign: Campaign name. Default None.
    """
    key = f"digest:{digest}"
    # If we want to reduce latency at all means, we could use a Bloom filter to check if the key exists
    # before hitting Redis. This way, we can avoid the round trip to Redis if the key does not exist.
    # Bloom filters are probabilistic data structures that can tell us if an element is in a set or not.
    # They are very fast and memory efficient, but they have a small probability of false positives:
    # 1) If the Bloom filter tells us that the key does not exist, then we can be sure that it does not exist.
    # 2) If the Bloom filter tells us that the key exists, then we have to hit Redis to be sure.
    url = rdb.get(key)
    if not url:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="URL Not Found")

    # TODO: Here we could capture some analytics about the URL, such as the number of times it was accessed,
    #  the IP addresses that accessed it, the source of the request (referrer), etc.
    #  We could also use this information to implement a more sophisticated rate limiting mechanism.
    log.debug("Redirecting to URL", url=url, digest=digest, referrer=referrer, campaign=campaign)

    return RedirectResponse(url)


class HealthCheckResponse(BaseModel):
    status: str


@app.get("/healthz", response_model=HealthCheckResponse)
def health():
    """
    Health check endpoint. Useful for liveness and readiness probes.
    """
    return {"status": "ok"}
