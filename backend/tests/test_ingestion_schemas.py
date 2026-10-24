import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.schemas import SnapshotInput


OFFICIAL_DATA = Path(__file__).resolve().parents[2] / "data" / "official.json"


def official_payload() -> dict:
    return json.loads(OFFICIAL_DATA.read_text(encoding="utf-8"))


def test_official_dataset_matches_snapshot_contract() -> None:
    snapshot = SnapshotInput.model_validate(official_payload())

    assert (len(snapshot.accounts), len(snapshot.services), len(snapshot.transactions)) == (
        10,
        30,
        100,
    )


def test_unknown_owner_is_rejected() -> None:
    payload = official_payload()
    payload["services"][0]["ownerId"] = 9999

    with pytest.raises(ValidationError, match="unknown ownerId"):
        SnapshotInput.model_validate(payload)


def test_unknown_service_is_rejected() -> None:
    payload = official_payload()
    payload["transactions"][0]["serviceId"] = 9999

    with pytest.raises(ValidationError, match="unknown serviceId"):
        SnapshotInput.model_validate(payload)


def test_invalid_service_status_is_rejected() -> None:
    payload = official_payload()
    payload["services"][0]["status"] = "unknown"

    with pytest.raises(ValidationError):
        SnapshotInput.model_validate(payload)


def test_performed_transaction_requires_timestamp() -> None:
    payload = official_payload()
    payload["transactions"][0]["performedAt"] = None

    with pytest.raises(ValidationError, match="performedAt is required"):
        SnapshotInput.model_validate(payload)