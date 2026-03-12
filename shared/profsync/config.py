from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "profsync"
    postgres_user: str = "profsync"
    postgres_password: str = "changeme"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379

    # predb.net
    predb_ws_url: str = ""
    predb_api_url: str = "https://api.predb.net/v1"
    predb_rate_limit: int = 60

    # xREL
    xrel_api_url: str = "https://api.xrel.to/v2"
    xrel_api_key: str = ""
    xrel_api_secret: str = ""

    # Analyzer
    analyzer_interval_minutes: int = 60

    # Logging
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
