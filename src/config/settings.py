import os
from typing import Optional
from pydantic import BaseModel, SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Infrastructure Configuration
# ---------------------------------------------------------------------------

class RazorpaySettings(BaseModel):
    """Infrastructure configuration for Razorpay."""
    key_id: str
    key_secret: SecretStr
    webhook_secret: SecretStr = Field(default=SecretStr(""))

class LLMSettings(BaseModel):
    """Infrastructure configuration for local/remote LLM."""
    base_url: str = Field(default="http://localhost:11434")
    model_name: str = Field(default="qwen3:8b")
    timeout_seconds: float = Field(default=120.0)

class DatabaseSettings(BaseModel):
    """Infrastructure configuration for the FCE database (PostgreSQL in production)."""
    url: SecretStr = Field(default=SecretStr("postgresql+psycopg://postgres:postgres@localhost:5432/fce"))

class ObservabilitySettings(BaseModel):
    """Infrastructure configuration for Telemetry & Logging."""
    log_format: str = Field(default="json")
    log_level: str = Field(default="INFO")
    metrics_port: int = Field(default=8000)

# ---------------------------------------------------------------------------
# Semantic Configuration
# ---------------------------------------------------------------------------

class ControlLoopSettings(BaseModel):
    """
    Semantic configuration governing FCE behavior.
    MUST NOT alter the authoritative financial-control logic, only timing & retry bounds.
    """
    worker_lease_ttl_seconds: int = Field(default=90)
    polling_interval_seconds: float = Field(default=1.0)
    max_retries: int = Field(default=3)
    retry_backoff_base_seconds: float = Field(default=2.0)
    event_stale_threshold_seconds: int = Field(default=300)


# ---------------------------------------------------------------------------
# Root Configuration
# ---------------------------------------------------------------------------

class FCESettings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__", extra="ignore")

    environment: str = Field(default="development", alias="ENVIRONMENT")

    razorpay: RazorpaySettings = Field(default_factory=lambda: RazorpaySettings(
        key_id=os.getenv("RAZORPAY_KEY_ID", ""),
        key_secret=os.getenv("RAZORPAY_KEY_SECRET", "")
    ))
    llm: LLMSettings = Field(default_factory=lambda: LLMSettings())
    database: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings(
        url=os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fce")
    ))
    observability: ObservabilitySettings = Field(default_factory=lambda: ObservabilitySettings())
    control_loop: ControlLoopSettings = Field(default_factory=lambda: ControlLoopSettings())

    @classmethod
    def load(cls) -> "FCESettings":
        """
        Loads the configuration.
        Forces strict environment precedence: 
        real env > .env (only in development/test) > defaults.
        """
        env = os.environ.get("ENVIRONMENT", "development").lower()
        
        # In production, we actively ignore any `.env` file that might have leaked
        env_file = ".env" if env in ("development", "test") else None
        
        # Pydantic SettingsConfigDict only applies to the class definition time
        # We can dynamically set the config dict kwargs when instantiating via _env_file
        return cls(_env_file=env_file, _env_nested_delimiter="__")

