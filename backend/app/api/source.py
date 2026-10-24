from fastapi import APIRouter, Depends, Request
from datetime import datetime, timezone

from ..auth.deps import require_user
from ..events import RecomputedEvent
from ..ingestion.loader import load_snapshot
from ..ingestion.schemas import SnapshotInput

router = APIRouter()


@router.put("/snapshot", dependencies=[Depends(require_user)])
def put_snapshot(snapshot: SnapshotInput, request: Request) -> dict[str, int]:
    result = load_snapshot(request.app.state.engine, snapshot)
    request.app.state.event_bus.publish(
        RecomputedEvent(result["modelVersion"], datetime.now(timezone.utc))
    )
    return result