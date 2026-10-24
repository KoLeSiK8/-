import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.ingestion.schemas import SnapshotInput
from app.main import create_app


OFFICIAL_DATA = Path(__file__).resolve().parents[2] / "data" / "official.json"


@pytest.fixture(scope="module")
def database_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL must point to an isolated PostgreSQL test database")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def client(database_engine: Engine):
    with TestClient(create_app(database_engine)) as test_client:
        response = test_client.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": settings.admin_password},
        )
        assert response.status_code == 200
        yield test_client


def official_payload() -> dict:
    return json.loads(OFFICIAL_DATA.read_text(encoding="utf-8"))


def test_startup_seeds_official_snapshot(client: TestClient, database_engine: Engine) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    with database_engine.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM public.accounts), "
                "(SELECT count(*) FROM public.services), "
                "(SELECT count(*) FROM public.transactions)"
            )
        ).one()
        score_counts = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM app.customer_scores), "
                "(SELECT count(*) FROM app.service_scores), "
                "(SELECT level FROM app.customer_scores WHERE customer_id = 5)"
            )
        ).one()
    assert counts == (10, 30, 100)
    assert score_counts == (10, 18, "high")


def test_invalid_snapshot_returns_422_without_mutating_database(
    client: TestClient, database_engine: Engine
) -> None:
    with database_engine.connect() as connection:
        before = connection.execute(
            text("SELECT id, status FROM public.services ORDER BY id")
        ).all()

    payload = official_payload()
    payload["services"][0]["status"] = "invalid"
    response = client.put("/api/v1/source/snapshot", json=payload)

    assert response.status_code == 422
    with database_engine.connect() as connection:
        after = connection.execute(
            text("SELECT id, status FROM public.services ORDER BY id")
        ).all()
    assert after == before


def test_snapshot_records_service_status_changes(
    client: TestClient, database_engine: Engine
) -> None:
    payload = official_payload()
    payload["services"][0]["status"] = "suspended"

    response = client.put("/api/v1/source/snapshot", json=payload)

    assert response.status_code == 200
    assert response.json()["changedStatuses"] == 1
    with database_engine.connect() as connection:
        event = connection.execute(
            text(
                "SELECT old_status, new_status FROM app.service_status_events "
                "WHERE service_id = 1 ORDER BY id DESC LIMIT 1"
            )
        ).one()
    assert event == ("active", "suspended")


def test_snapshot_rolls_back_when_recompute_fails(
    database_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ingestion import loader

    with database_engine.connect() as connection:
        before_services = connection.execute(
            text("SELECT id, status FROM public.services ORDER BY id")
        ).all()
        before_events = connection.execute(
            text("SELECT count(*) FROM app.service_status_events")
        ).scalar_one()

    payload = official_payload()
    payload["services"][0]["status"] = "suspended"
    snapshot = SnapshotInput.model_validate(payload)

    def fail_recompute(*args, **kwargs):
        raise RuntimeError("recompute failed")

    monkeypatch.setattr(loader, "recompute", fail_recompute)
    with pytest.raises(RuntimeError, match="recompute failed"):
        loader.load_snapshot(database_engine, snapshot)

    with database_engine.connect() as connection:
        after_services = connection.execute(
            text("SELECT id, status FROM public.services ORDER BY id")
        ).all()
        after_events = connection.execute(
            text("SELECT count(*) FROM app.service_status_events")
        ).scalar_one()
    assert after_services == before_services
    assert after_events == before_events


@pytest.mark.parametrize(
    "sort_by,key",
    [
        ("id", "id"),
        ("email", "email"),
        ("balance", "balanceCents"),
        ("total_replenished", "totalReplenishedCents"),
    ],
)
@pytest.mark.parametrize("order,reverse", [("asc", False), ("desc", True)])
def test_customer_sorting(
    client: TestClient, sort_by: str, key: str, order: str, reverse: bool
) -> None:
    response = client.get(
        "/api/v1/customers",
        params={"sort_by": sort_by, "order": order, "size": 50},
    )

    assert response.status_code == 200
    values = [item[key] for item in response.json()["items"]]
    assert values == sorted(values, reverse=reverse)


def test_customer_filter_search_and_detail(client: TestClient) -> None:
    filtered = client.get("/api/v1/customers", params={"level": "high", "q": "user-0005"})
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [5]

    detail = client.get("/api/v1/customers/5")
    assert detail.status_code == 200
    assert detail.json()["level"] == "high"
    assert detail.json()["services"]
    assert detail.json()["reasons"]


def test_analytics_summary_and_timeline(client: TestClient) -> None:
    summary = client.get("/api/v1/analytics/summary")
    timeline = client.get("/api/v1/analytics/churn-timeline")

    assert summary.status_code == 200
    assert summary.json()["counts"]["high"] >= 1
    assert summary.json()["expectedLossCents"] > 0
    assert timeline.status_code == 200
    assert {item["type"] for item in timeline.json()["series"]} == {
        "observed",
        "estimated",
        "forecast",
    }


def test_patch_model_settings_changes_scores_and_version(
    client: TestClient, database_engine: Engine
) -> None:
    before_score = client.get("/api/v1/customers/5").json()["score"]
    before_version = client.get("/api/v1/model/settings").json()["version"]

    response = client.patch(
        "/api/v1/model/settings",
        json={"weights": {"funds_deficit": 50}},
    )

    assert response.status_code == 200
    assert response.json()["version"] == before_version + 1
    assert client.get("/api/v1/customers/5").json()["score"] != before_score

    with TestClient(create_app(database_engine)) as restarted:
        login = restarted.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": settings.admin_password},
        )
        assert login.status_code == 200
        persisted = restarted.get("/api/v1/model/settings").json()
    assert persisted["version"] == response.json()["version"]
    assert persisted["settings"]["weights"]["funds_deficit"] == 50


def test_patch_rejects_invalid_thresholds(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/model/settings",
        json={"thresholds": {"low": 80, "high": 65}},
    )

    assert response.status_code == 422