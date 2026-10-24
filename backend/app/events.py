import asyncio
from dataclasses import dataclass
from datetime import datetime
from threading import Lock


@dataclass(frozen=True)
class RecomputedEvent:
    model_version: int
    at: datetime


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[
            asyncio.Queue[RecomputedEvent], asyncio.AbstractEventLoop | None
        ] = {}
        self._lock = Lock()

    def subscribe(self) -> asyncio.Queue[RecomputedEvent]:
        queue: asyncio.Queue[RecomputedEvent] = asyncio.Queue()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        with self._lock:
            self._subscribers[queue] = loop
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RecomputedEvent]) -> None:
        with self._lock:
            self._subscribers.pop(queue, None)

    def publish(self, event: RecomputedEvent) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.items())
        for queue, loop in subscribers:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(queue.put_nowait, event)
            else:
                queue.put_nowait(event)