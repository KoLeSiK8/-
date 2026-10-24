from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from datetime import datetime, timezone

from ..auth.deps import require_user
from ..scoring.recompute import load_settings, recompute, save_settings
from ..scoring.settings import ScoringSettings, feature_descriptions
from ..events import RecomputedEvent

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/settings")
def get_settings(request: Request) -> dict:
    settings, version = load_settings(request.app.state.engine)
    return {
        "settings": settings.model_dump(mode="json"),
        "version": version,
        "features": feature_descriptions(),
        "ranges": {
            "weights": [0, 100],
            "thresholds": [0, 100],
            "alpha_max_mean": [0, 1],
            "horizon_days": [0.001, 3650],
            "horizon_money_days": [0.001, 3650],
        },
    }


@router.patch("/settings")
def patch_settings(payload: dict[str, Any], request: Request) -> dict:
    engine = request.app.state.engine
    current, _ = load_settings(engine)
    merged = current.model_dump(mode="json")
    incoming = dict(payload)
    for nested_key in ("weights", "thresholds", "churn_curve"):
        if isinstance(incoming.get(nested_key), dict):
            merged[nested_key].update(incoming.pop(nested_key))
    merged.update(incoming)
    try:
        validated = ScoringSettings.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    version = save_settings(engine, validated)
    recomputed = recompute(engine)
    request.app.state.event_bus.publish(
        RecomputedEvent(version, datetime.now(timezone.utc))
    )
    return {
        "settings": validated.model_dump(mode="json"),
        "version": version,
        "asOf": recomputed["asOf"],
        "calculatedAt": recomputed["calculatedAt"],
    }