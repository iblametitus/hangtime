from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All model IDs and secrets come from here, never hardcoded elsewhere."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nebius_api_key: str = ""
    tavily_api_key: str = ""

    token_factory_base_url: str = "https://api.tokenfactory.nebius.com/v1/"

    # Candidate IDs from docs/SPEC.md section 2. UNCONFIRMED until
    # scripts/check_models.py has run against the real account (milestone M0).
    model_fast: str = "nvidia/Nemotron-3_5-Lightning"
    model_vision: str = "nvidia/Nemotron-3.5-Super-VL"
    model_reason: str = "nvidia/Nemotron-3-Ultra-550b-a55b"
    model_audio: str = ""

    db_path: str = "data/hangtime.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
