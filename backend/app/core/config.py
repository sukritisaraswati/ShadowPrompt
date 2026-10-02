"""Application configuration.

Settings are loaded from environment variables (and a local .env file in
development). Nothing in here is ever logged verbatim -- see
``app.core.logging`` for the redaction filter that protects secrets.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the ShadowPrompt backend."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    app_name: str = "ShadowPrompt"
    api_v1_prefix: str = "/api/v1"
    shadowprompt_env: str = "development"
    shadowprompt_debug: bool = True
    shadowprompt_log_level: str = "INFO"

    # --- Database ---
    # Default is the SQLite fallback so a fresh clone runs with no external
    # services. Docker Compose overrides this with the PostgreSQL URL.
    database_url: str = "sqlite+aiosqlite:///./shadowprompt.db"
    database_echo: bool = False

    # --- CORS ---
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])

    # --- Layer 3 meta-evaluator (Release 3) ---
    anthropic_api_key: str | None = None
    layer3_model: str = "claude-sonnet-5-5"
    # Ceiling on judge calls per campaign, to bound platform API spend.
    layer3_max_calls_per_campaign: int = 40
    layer3_enabled: bool = False

    # --- Outbound fetch limits (ShadowScan SSRF controls, Release 1) ---
    fetch_timeout_seconds: float = 10.0
    fetch_max_redirects: int = 3
    fetch_max_bytes: int = 5 * 1024 * 1024
    upload_max_bytes: int = 2 * 1024 * 1024
    scanner_user_agent: str = "ShadowScan/0.2 (+defensive prompt-injection scanner)"

    # --- Reports ---
    reports_dir: str = "generated_reports"

    # --- LLM proxy limits (Lab, Release 2) ---
    llm_timeout_seconds: float = 60.0
    llm_max_response_bytes: int = 1024 * 1024
    # Kept small: a refusal or a leaked canary shows up in the first few
    # sentences, and short replies keep the user's API costs down.
    llm_max_output_tokens: int = 400
    llm_retry_base_delay: float = 1.0
    # Allows LLM endpoints on loopback and private networks, for self-hosted
    # deployments testing local models. Off by default; cloud metadata
    # addresses stay blocked regardless. Never applies to ShadowScan.
    llm_allow_private_endpoints: bool = False
    max_concurrent_campaigns: int = 3

    # --- Custom payload packs (Lab, Phase 4) ---
    custom_packs_enabled: bool = True
    # Cap on stored packs, so anonymous uploads cannot fill the database.
    custom_packs_max_stored: int = 200
    rate_limit_pack_uploads_per_hour: int = 20

    # --- Rate limiting ---
    rate_limit_scans_per_minute: int = 10
    rate_limit_campaigns_per_hour: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string from the environment."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        """True when running against the local SQLite fallback."""
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()
