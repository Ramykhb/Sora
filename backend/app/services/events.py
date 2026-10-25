import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from uuid import UUID


class Events:
    def __init__(self):
        self.subscribers = defaultdict(set)

    def publish(self, session_id: UUID, event: dict):
        for queue in tuple(self.subscribers.get(session_id, ())):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, session_id: UUID):
        if len(self.subscribers[session_id]) >= 20:
            raise ValueError("Too many event subscribers")
        queue = asyncio.Queue(maxsize=32)
        self.subscribers[session_id].add(queue)
        try:
            yield queue
        finally:
            self.subscribers[session_id].discard(queue)
            if not self.subscribers[session_id]:
                self.subscribers.pop(session_id, None)


events = Events()
