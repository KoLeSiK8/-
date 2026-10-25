

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DATA = ROOT / "data" / "official.json"


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
        assert test_client.post("/api/v1/source/presets/official").status_code == 200
        yield test_client
        test_client.post("/api/v1/source/presets/official")


def official_payload() -> dict:
    return json.loads(OFFICIAL_DATA.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "payload",
    [
        {"thresholds": {"low": 80, "high": 65}},
        {"weights": {"funds_deficit": 150}},
        {"weights": {"no_such_feature": 1}},
        {"as_of_mode": "fixed", "as_of_fixed": None},
        {"horizon_days": 0},
        {"unknown_setting": 1},
    ],
)
def test_invalid_settings_return_422_and_keep_version(client: TestClient, payload: dict) -> None:
    before = client.get("/api/v1/model/settings").json()["version"]

    response = client.patch("/api/v1/model/settings", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get("/api/v1/model/settings").json()["version"] == before


def test_settings_expose_feature_descriptions_and_defaults(client: TestClient) -> None:
    body = client.get("/api/v1/model/settings").json()

    assert body["defaults"]["thresholds"] == {"low": 35, "high": 65}
    assert all(item["description"] != item["title"] for item in body["features"])


def test_forged_or_malformed_session_cookie_is_401(database_engine: Engine) -> None:
    with TestClient(create_app(database_engine)) as anonymous:
        for value in ("not-a-uuid", "00000000-0000-0000-0000-000000000000.bad", "x.y.z"):
            anonymous.cookies.set("session", value)
            assert anonymous.get("/api/v1/auth/me").status_code == 401


def test_switching_datasets_records_no_fake_status_changes(
    client: TestClient, database_engine: Engine
) -> None:
    with database_engine.connect() as connection:
        before = connection.execute(
            text("SELECT count(*) FROM app.service_status_events")
        ).scalar_one()

    demo = client.post("/api/v1/source/presets/demo")
    official = client.post("/api/v1/source/presets/official")

    assert demo.status_code == 200
    assert demo.json()["changedStatuses"] == 0
    assert official.json()["changedStatuses"] == 0
    with database_engine.connect() as connection:
        after = connection.execute(
            text("SELECT count(*) FROM app.service_status_events")
        ).scalar_one()
    assert after == before


def test_real_status_change_is_still_recorded(client: TestClient) -> None:
    payload = official_payload()
    payload["services"][1]["status"] = "deleted"

    response = client.put("/api/v1/source/snapshot", json=payload)

    assert response.json()["changedStatuses"] == 1
    assert client.post("/api/v1/source/presets/official").json()["changedStatuses"] == 1


def test_summary_counts_match_customer_table(client: TestClient) -> None:
    summary = client.get("/api/v1/analytics/summary").json()

    for level, count in summary["counts"].items():
        page = client.get("/api/v1/customers", params={"level": level, "size": 1}).json()
        assert page["total"] == count
    expected = sum(
        item["expectedLossCents"]
        for item in client.get("/api/v1/customers", params={"size": 200}).json()["items"]
    )
    assert summary["expectedLossCents"] == expected


def test_summary_reads_stored_result_instead_of_recalculating(
    client: TestClient, database_engine: Engine
) -> None:
    before = client.get("/api/v1/analytics/summary").json()
    with database_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE app.model_settings SET settings = jsonb_set(settings, "
                "'{weights,funds_deficit}', '100')"
            )
        )
    try:
        assert client.get("/api/v1/analytics/summary").json() == before
    finally:
        with database_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app.model_settings SET settings = jsonb_set(settings, "
                    "'{weights,funds_deficit}', '25')"
                )
            )


def test_timeline_uses_one_unit(client: TestClient) -> None:
    client.post("/api/v1/source/presets/demo")
    try:
        timeline = client.get("/api/v1/analytics/churn-timeline").json()
    finally:
        client.post("/api/v1/source/presets/official")

    assert timeline["unit"] == "services"
    series = {item["type"]: item["points"] for item in timeline["series"]}
    assert series["estimated"], "demo data has deleted services"
    assert series["forecast"], "demo data has services expiring soon"

    assert max(point["value"] for point in series["estimated"]) < 480
    assert all(float(point["value"]).is_integer() for point in series["estimated"])


def test_explanations_show_money_in_euros(client: TestClient) -> None:
    detail = client.get("/api/v1/customers/5").json()
    explanations = [
        item["explanation"]
        for service in detail["services"]
        for item in service["featureContributions"]
    ]

    assert any("€" in text for text in explanations)


def test_snapshot_without_timezone_is_treated_as_utc(client: TestClient) -> None:
    payload = official_payload()
    payload["capturedAt"] = "2026-10-19T14:35:53"
    for service in payload["services"]:
        service["createdAt"] = service["createdAt"].removesuffix("Z")

    response = client.put("/api/v1/source/snapshot", json=payload)

    assert response.status_code == 200
    assert client.get("/api/v1/analytics/summary").json()["asOf"].startswith(
        "2026-10-19T14:35:53"
    )
    client.post("/api/v1/source/presets/official")


def test_search_treats_wildcards_literally(client: TestClient) -> None:
    assert client.get("/api/v1/customers", params={"q": "%"}).json()["total"] == 0
    assert client.get("/api/v1/customers", params={"q": "_"}).json()["total"] == 0


def test_concurrent_writes_do_not_fail(client: TestClient) -> None:
    def patch(weight: int) -> int:
        return client.patch(
            "/api/v1/model/settings", json={"weights": {"withdraw_leak": weight}}
        ).status_code

    def put(_: int) -> int:
        return client.put("/api/v1/source/snapshot", json=official_payload()).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(patch, range(1, 9))) + list(pool.map(put, range(4)))

    assert set(results) == {200}
    client.patch("/api/v1/model/settings", json={"weights": {"withdraw_leak": 5}})


def test_stored_settings_survive_feature_changes(
    client: TestClient, database_engine: Engine
) -> None:
    with database_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE app.model_settings SET settings = jsonb_set("
                "settings #- '{weights,withdraw_leak}', '{weights,removed_feature}', '7')"
            )
        )
    try:
        body = client.get("/api/v1/model/settings").json()
        assert "removed_feature" not in body["settings"]["weights"]
        assert body["settings"]["weights"]["withdraw_leak"] == 5
        assert client.patch(
            "/api/v1/model/settings", json={"weights": {"withdraw_leak": 5}}
        ).status_code == 200
    finally:
        client.patch("/api/v1/model/settings", json={"weights": {"withdraw_leak": 5}})


def test_demo_step2_feeds_observed_churn(client: TestClient) -> None:
    client.post("/api/v1/source/presets/demo")
    before = client.get("/api/v1/analytics/summary").json()
    try:
        step2 = client.post("/api/v1/source/presets/demo-step2")
        after = client.get("/api/v1/analytics/summary").json()
        timeline = client.get("/api/v1/analytics/churn-timeline").json()
    finally:
        client.post("/api/v1/source/presets/official")

    assert step2.status_code == 200
    assert step2.json()["changedStatuses"] > 0
    assert after["counts"]["high"] < before["counts"]["high"]
    observed = next(item for item in timeline["series"] if item["type"] == "observed")
    assert sum(point["value"] for point in observed["points"]) > 0
