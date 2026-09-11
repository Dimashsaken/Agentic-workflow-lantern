"""Configuration: environment variables only (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_url: str
    app_name: str = "Tender"


def load_settings() -> Settings:
    return Settings(
        secret_key=os.environ.get("TENDER_SECRET_KEY", "dev-only-secret"),
        database_url=os.environ.get("TENDER_DATABASE_URL", "sqlite:///./tender.db"),
    )
