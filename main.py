"""Application factory.

Run with:  uvicorn ecopulse.main:create_app --factory --reload
"""

from fastapi import FastAPI

from . import __version__
from .api import router
from .config import Settings, load_settings
from .recommendations.gemini_client import GeminiClient
from .services import build_services

DESCRIPTION = """
EcoPulse logs daily activities (travel, electricity, cooking fuel, meals, waste),
estimates their CO2-equivalent using localised carbon intensity data, and suggests
personalised habit changes.

Interactive docs are below. Emission factors are approximate; see the methodology
notes in the repository before relying on the numbers.
"""


def create_app(settings: Settings | None = None, gemini: GeminiClient | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="EcoPulse", version=__version__, description=DESCRIPTION)
    app.state.services = build_services(settings, gemini)
    app.include_router(router)
    return app
