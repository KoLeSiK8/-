from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from ..auth.deps import require_user
from ..events import RecomputedEvent
from ..scoring.lock import RECOMPUTE_LOCK
from ..scoring.recompute import load_settings, recompute, save_settings
from ..scoring.settings import ScoringSettings, feature_descriptions

router = APIRouter(dependencies=[Depends(require_user)])
NESTED_KEYS = ("weights", "thresholds", "churn_curve")


def validation_detail(exc: ValidationError) -> list[dict[str, Any]]:

    return exc.errors(include_url=False, include_context=False, include_input=False)


@router.get("/settings", summary="Настройки модели, значения по умолчанию и описания признаков")
def get_settings(request: Request) -> dict:
    settings, version = load_settings(request.app.state.engine)
    defaults = ScoringSettings()
    return {
        "settings": settings.model_dump(mode="json"),
        "defaults": defaults.model_dump(mode="json"),
        "version": version,
        "features": feature_descriptions(),
        "ranges": {
            "weights": [0, 100],
            "thresholds": [0, 100],
            "alpha_max_mean": [0, 1],
            "horizon_days": [0.001, 3650],
            "horizon_money_days": [0.001, 3650],
            "churn_curve.k": [0.0001, 10],
            "churn_curve.midpoint": [0, 100],
            "balance_shield": [0, 1],
            "suspended_value": [0, 1],
        },
    }


@router.patch("/settings", summary="Частично изменить настройки и пересчитать оценки")
def patch_settings(request: Request, payload: dict[str, Any] = Body(...)) -> dict:
    engine = request.app.state.engine
    with RECOMPUTE_LOCK:
        current, _ = load_settings(engine)
        merged = current.model_dump(mode="json")
        incoming = dict(payload)
        for nested_key in NESTED_KEYS:
            if isinstance(incoming.get(nested_key), dict):
                merged[nested_key].update(incoming.pop(nested_key))
        merged.update(incoming)
        try:
            validated = ScoringSettings.model_validate(merged)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=validation_detail(exc)) from exc

        connection = engine.raw_connection()
        try:
            version = save_settings(engine, validated, connection=connection)
            recomputed = recompute(
                engine, connection=connection, settings=validated, version=version
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    request.app.state.event_bus.publish(RecomputedEvent(version, datetime.now(timezone.utc)))
    return {
        "settings": validated.model_dump(mode="json"),
        "version": version,
        "asOf": recomputed["asOf"],
        "calculatedAt": recomputed["calculatedAt"],
    }
