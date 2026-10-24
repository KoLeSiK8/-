import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..auth.deps import require_user
from ..events import EventBus

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("", summary="SSE-поток: событие recomputed после каждого пересчёта")
async def stream_events(request: Request) -> StreamingResponse:
    bus: EventBus = request.app.state.event_bus
    queue = bus.subscribe()

    async def event_stream():
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                payload = json.dumps(
                    {"modelVersion": event.model_version, "at": event.at.isoformat()}
                )
                yield f"event: recomputed\ndata: {payload}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )