import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import settings
from app.main import create_app


@pytest.fixture(scope="module")
def database_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL must point to an isolated PostgreSQL test database")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


def test_protected_endpoints_require_session(database_engine: Engine) -> None:
    with TestClient(create_app(database_engine)) as client:
        protected_gets = (
            "/api/v1/auth/me",
            "/api/v1/customers",
            "/api/v1/customers/1",
            "/api/v1/analytics/summary",
            "/api/v1/analytics/churn-timeline",
            "/api/v1/model/settings",
        )
        assert all(client.get(path).status_code == 401 for path in protected_gets)
        assert client.put("/api/v1/source/snapshot", json={}).status_code == 401
        assert client.patch("/api/v1/model/settings", json={}).status_code == 401


def test_admin_login_me_and_logout(database_engine: Engine) -> None:
    with TestClient(create_app(database_engine)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": settings.admin_password},
        )
        assert login.status_code == 200
        assert "session" in login.cookies

        current_user = client.get("/api/v1/auth/me")
        assert current_user.status_code == 200
        assert current_user.json() == {"login": settings.admin_login}

        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_password_is_rejected(database_engine: Engine) -> None:
    with TestClient(create_app(database_engine)) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": "incorrect"},
        )

    assert response.status_code == 401


