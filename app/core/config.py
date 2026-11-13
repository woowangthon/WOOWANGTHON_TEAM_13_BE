from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 0
    db_pool_timeout_seconds: float = 10

    supabase_url: str
    supabase_secret_key: str = ""
    supabase_storage_bucket: str = "content-files"
    supabase_store_photo_bucket: str = "store-photos"
    supabase_jwt_issuer: str
    supabase_jwt_audience: str = "authenticated"
    supabase_jwks_url: str

    cors_origins: str = "http://localhost:5173"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: float = 20

    nts_business_api_key: str = ""

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    # Values are populated by pydantic-settings from environment variables.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
