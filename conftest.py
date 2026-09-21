import pytest
from fastapi.testclient import TestClient

from ecopulse.config import Settings
from ecopulse.main import create_app
from ecopulse.services import build_services


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "test.db"), gemini_api_key=None)


@pytest.fixture
def services(settings):
    return build_services(settings)


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))
