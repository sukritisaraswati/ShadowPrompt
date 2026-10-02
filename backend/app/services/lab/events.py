"""In-process event bus for live campaign progress (Server-Sent Events).

The orchestrator publishes an event after every saved result and every status
change. Each open SSE connection holds a bounded queue. A slow or abandoned
client can only lose events, never block a campaign: a client that falls
behind receives a ``resync`` event and reloads the campaign snapshot.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

QUEUE_SIZE = 500


class CampaignEvents:
    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, campaign_id: uuid.UUID) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.setdefault(campaign_id, set()).add(queue)
        return queue

    def unsubscribe(self, campaign_id: uuid.UUID, queue: asyncio.Queue[dict[str, Any]]) -> None:
        queues = self._subscribers.get(campaign_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            del self._subscribers[campaign_id]

    def publish(self, campaign_id: uuid.UUID, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(campaign_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Replace the backlog with one instruction to reload.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "resync"})

    def subscriber_count(self, campaign_id: uuid.UUID) -> int:
        return len(self._subscribers.get(campaign_id, ()))


events = CampaignEvents()
