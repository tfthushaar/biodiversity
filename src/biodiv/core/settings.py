from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    iucn_api_token: str = ""
    ebird_api_key: str = ""

    # Models for the live demo endpoint. Unset means that endpoint reports itself unavailable.
    megadetector_onnx: str = ""
    backbone_onnx: str = ""
    heads_dir: str = "models/heads"

    # Public endpoint hygiene.
    cors_origins: str = "*"  # comma-separated; the API is read-only and uses no cookies
    max_upload_mb: int = 8
    infer_requests_per_minute: int = 10

    # Be a polite client: identify ourselves to public APIs.
    user_agent: str = "biodiv/0.1 (+https://github.com/tfthushaar/biodiversity)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
