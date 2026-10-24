import json
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import settings
from app.main import create_app
from app.analytics.summary import build_summary
from app.api.events import stream_events
from app.events import RecomputedEvent

OFFICIAL_DATA = Path(__file__).resolve().parents[2] / "data" / "official.json"


@pytest.fixture(scope="module")
def database_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL must point to an isolated PostgreSQL test database")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def client(database_engine: Engine):
    with TestClient(create_app(database_engine)) as test_client:
        response = test_client.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": settings.admin_password},
        )
        assert response.status_code == 200
        yield test_client


def test_metrics_aliases_require_auth_and_bearer_works(database_engine: Engine) -> None:
    with TestClient(create_app(database_engine)) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metics").status_code == 401

        metrics = client.get(
            "/metrics", headers={"Authorization": f"Bearer {settings.metrics_token}"}
        )
        alias = client.get(
            "/metics", headers={"Authorization": f"Bearer {settings.metrics_token}"}
        )
    assert metrics.status_code == 200
    assert alias.status_code == 200
    assert "churn_customers" in metrics.text


def test_prometheus_values_match_build_summary(database_engine: Engine) -> None:
    with TestClient(create_app(database_engine)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"login": settings.admin_login, "password": settings.admin_password},
        )
        assert login.status_code == 200
        exposition = client.get("/metrics").text

    parsed = {
        sample.name
        + (
            "{" + ",".join(f'{key}="{value}"' for key, value in sample.labels.items()) + "}"
            if sample.labels
            else ""
        ): sample.value
        for family in text_string_to_metric_families(exposition)
        for sample in family.samples
    }
    summary = build_summary(database_engine)

    assert parsed["churn_revenue_at_risk_eur"] == summary["revenueAtRiskCents"] / 100
    assert parsed["churn_expected_loss_eur"] == summary["expectedLossCents"] / 100
    assert parsed["churn_recoverable_eur"] == summary["recoverableCents"] / 100
    assert parsed["churn_lost_revenue_monthly_eur"] == (
        summary["lostRevenueMonthlyCents"] / 100
    )
    for level, count in summary["counts"].items():
        assert parsed[f'churn_customers{{level="{level}"}}'] == count


def test_sse_publishes_recomputed_after_patch_and_put(
    client: TestClient, database_engine: Engine
) -> None:
    bus = client.app.state.event_bus
    queue = bus.subscribe()
    patch = client.patch(
        "/api/v1/model/settings",
        json={"weights": {"funds_deficit": 26}},
    )
    snapshot_response = client.put(
        "/api/v1/source/snapshot",
        json=json.loads(OFFICIAL_DATA.read_text(encoding="utf-8")),
    )

    assert patch.status_code == 200
    assert snapshot_response.status_code == 200
    assert queue.get_nowait().model_version == patch.json()["version"]
    assert queue.get_nowait().model_version == snapshot_response.json()["modelVersion"]
    bus.unsubscribe(queue)


def test_sse_stream_encodes_recomputed_event() -> None:
    async def run_stream() -> tuple[str, str]:
        from app.events import EventBus

        bus = EventBus()

        async def connected_request() -> bool:
            return False

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(event_bus=bus)),
            is_disconnected=connected_request,
        )
        response = await stream_events(request)
        stream = response.body_iterator
        connected = await anext(stream)
        await asyncio.to_thread(
            bus.publish,
            RecomputedEvent(7, datetime(2026, 10, 24, tzinfo=timezone.utc)),
        )
        message = await anext(stream)
        await stream.aclose()
        return connected, message

    connected, message = asyncio.run(run_stream())

    assert connected == ": connected\n\n"
    assert message.startswith("event: recomputed\ndata: ")
    assert '"modelVersion": 7' in message