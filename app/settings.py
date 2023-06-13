from pathlib import Path
from typing import Optional

import structlog
from pydantic import BaseSettings

log = structlog.get_logger("url-shortening-app.settings")


class Settings(BaseSettings):
    redis_host: str = "0.0.0.0"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0

    # Sentry integration is optional. If you don't want to use it, just leave the `sentry_dsn` env variable empty.
    sentry_dsn: Optional[str] = None
    sentry_traces_sample_rate: float = 1.0
    sentry_profiles_sample_rate: float = 1.0

    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"

        if Path(env_file).exists():
            log.info("Loading environment variables from file", env_file=env_file)


settings = Settings()
