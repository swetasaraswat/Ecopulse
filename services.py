"""Wires the pieces together so the API, tests and scripts share one setup."""

from dataclasses import dataclass

from .config import Settings
from .emissions import EmissionCalculator, FactorStore
from .recommendations import RecommendationEngine
from .recommendations.gemini_client import GeminiClient
from .storage import Storage


@dataclass
class Services:
    settings: Settings
    storage: Storage
    factors: FactorStore
    calculator: EmissionCalculator
    engine: RecommendationEngine
    ai_enabled: bool


def build_services(settings: Settings, gemini: GeminiClient | None = None) -> Services:
    if gemini is None and settings.gemini_api_key:
        gemini = GeminiClient(settings.gemini_api_key, settings.gemini_model)
    storage = Storage(settings.db_path)
    factors = FactorStore()
    calculator = EmissionCalculator(factors)
    engine = RecommendationEngine(storage, calculator, gemini)
    return Services(settings, storage, factors, calculator, engine, ai_enabled=gemini is not None)
