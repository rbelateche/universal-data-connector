"""The optional X-Api-Key guard for public deployments."""

from pathlib import Path

from fastapi.testclient import TestClient

from udc.api.app import create_app
from udc.api.dependencies import _reset_singletons
from udc.core.config import Settings, get_settings


def _client(tmp_path: Path, require: bool) -> TestClient:
    _reset_singletons()
    settings = Settings(
        database_url="postgresql://unused@localhost/unused",
        duckdb_path=str(tmp_path / "k.duckdb"),
        api_key="s3cret-key",
        require_api_key=require,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_guard_is_off_by_default(tmp_path: Path) -> None:
    assert _client(tmp_path, require=False).get("/sources").status_code == 200


def test_guard_requires_the_key(tmp_path: Path) -> None:
    client = _client(tmp_path, require=True)
    assert client.get("/sources").status_code == 401
    assert client.get("/sources", headers={"X-Api-Key": "wrong"}).status_code == 401
    assert client.get("/sources", headers={"X-Api-Key": "s3cret-key"}).status_code == 200
    assert client.get("/coverage", headers={"X-Api-Key": "s3cret-key"}).status_code == 200


def test_health_stays_open(tmp_path: Path) -> None:
    assert _client(tmp_path, require=True).get("/health").status_code == 200
