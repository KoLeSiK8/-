import asyncio
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RecomputedEvent:
    model_version: int
    at: datetime


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[RecomputedEvent]] = set()

    def subscribe(self) -> asyncio.Queue[RecomputedEvent]:
        queue: asyncio.Queue[RecomputedEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RecomputedEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: RecomputedEvent) -> None:
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)