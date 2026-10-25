import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from ..auth.deps import require_user
from ..config import dataset_path
from ..events import RecomputedEvent
from ..ingestion.loader import load_snapshot
from ..ingestion.schemas import SnapshotInput
from .model import validation_detail

router = APIRouter(dependencies=[Depends(require_user)])


def _apply(snapshot: SnapshotInput, request: Request) -> dict[str, int]:
    result = load_snapshot(request.app.state.engine, snapshot)
    request.app.state.event_bus.publish(
        RecomputedEvent(result["modelVersion"], datetime.now(timezone.utc))
    )
    return result


@router.put("/snapshot", summary="Заменить снимок данных и пересчитать оценки")
def put_snapshot(snapshot: SnapshotInput, request: Request) -> dict[str, int]:
    return _apply(snapshot, request)


@router.post(
    "/presets/{name}",
    summary="Загрузить встроенный набор: official, demo или demo-step2 (демо через сутки)",
)
def load_preset(
    name: Literal["official", "demo", "demo-step2"], request: Request
) -> dict[str, int]:

    path = dataset_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Dataset {name} is not bundled")
    try:
        snapshot = SnapshotInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=validation_detail(exc)) from exc
    return _apply(snapshot, request)
