"""Smoke test for the FastAPI app factory."""

import pytest
from fastapi.testclient import TestClient

from udc.api.app import create_app
from udc.core.config import Settings, get_settings


@pytest.fixture
def client() -> TestClient:
    def override_settings() -> Settings:
        return Settings(
            database_url="postgresql+asyncpg://user:pass@localhost/test",
            anthropic_api_key="sk-ant-test",
        )

    app = create_app()
    app.dependency_overrides[get_settings] = override_settings
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
