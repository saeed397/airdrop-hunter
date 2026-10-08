"""Application configuration loaded from environment variables."""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """All configuration via environment variables."""

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://user:pass@localhost:5432/airdrop_hunter",
        description="Postgres connection string (Neon/Supabase recommended)"
    )

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # API Keys (optional free tiers)
    ETHERSCAN_API_KEY: Optional[str] = None
    GOPLUS_API_KEY: Optional[str] = None

    # Scoring & Scanning
    ALERT_SCORE_THRESHOLD: int = Field(default=60, ge=0, le=100)
    SCAN_INTERVAL_MINUTES: int = Field(default=30, ge=5)

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
