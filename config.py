"""Runtime settings, read from environment variables (and a .env file if present)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_path: str = "ecopulse.db"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    default_region: str = "IN"


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        db_path=os.environ.get("ECOPULSE_DB", "ecopulse.db"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        default_region=os.environ.get("ECOPULSE_DEFAULT_REGION", "IN").upper(),
    )
