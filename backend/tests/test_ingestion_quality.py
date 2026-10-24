import json
from pathlib import Path

from app.ingestion.quality import find_quality_warnings
from app.ingestion.schemas import SnapshotInput


OFFICIAL_DATA = Path(__file__).resolve().parents[2] / "data" / "official.json"


def test_quality_warnings_cover_expired_and_funded_prolong_wait_services() -> None:
    payload = json.loads(OFFICIAL_DATA.read_text(encoding="utf-8"))
    payload["capturedAt"] = "2026-10-24T00:00:00.000Z"
    payload["services"][4]["autoProlong"] = True
    snapshot = SnapshotInput.model_validate(payload)

    warnings = find_quality_warnings(snapshot)
    codes_by_service = {
        service_id: {warning["code"] for warning in warnings if warning["serviceId"] == service_id}
        for service_id in {warning["serviceId"] for warning in warnings}
    }

    assert "expired_live_service" in codes_by_service[1]
    assert codes_by_service[5] == {
        "prolong_wait_overdue",
        "prolong_wait_funded_autoprolong",
    }