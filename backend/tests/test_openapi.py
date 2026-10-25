from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from app.main import create_app  

OPENAPI_FILE = Path(__file__).resolve().parents[2] / "openapi.yml"


def test_openapi_file_matches_live_schema() -> None:
    if not OPENAPI_FILE.is_file():
        pytest.skip("openapi.yml is not shipped next to the tests (e.g. inside the API image)")
    committed = yaml.safe_load(OPENAPI_FILE.read_text(encoding="utf-8"))
    live = create_app().openapi()

    assert committed == live, "openapi.yml is stale: run `make openapi`"


def test_public_and_protected_paths_are_documented() -> None:
    paths = create_app().openapi()["paths"]

    for path in (
        "/healthz",
        "/api/v1/auth/login",
        "/api/v1/customers",
        "/api/v1/customers/{customer_id}",
        "/api/v1/analytics/summary",
        "/api/v1/analytics/churn-timeline",
        "/api/v1/model/settings",
        "/api/v1/source/snapshot",
        "/api/v1/source/presets/{name}",
        "/api/v1/events",
        "/metrics",
        "/metics",
    ):
        assert path in paths
