"""Runtime configuration.

Everything the service needs comes from the environment so that the same image
runs unchanged on Docker Compose, EKS or GKE. No cloud SDKs, no provider
specific metadata lookups -- that is what keeps the workload cloud-agnostic.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "idea-board-api"
    # Populated by the platform (Helm values / compose) purely for observability.
    environment: str = Field(default="local")
    cloud: str = Field(default="local")
    release_version: str = Field(default="dev")

    database_url: str = Field(
        default="postgresql+asyncpg://ideas:ideas@db:5432/ideas",
        description="SQLAlchemy async DSN. Injected from a secret in-cluster.",
    )
    db_pool_size: int = 5
    db_max_overflow: int = 5

    cors_allow_origins: str = "*"
    max_idea_length: int = 500

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
