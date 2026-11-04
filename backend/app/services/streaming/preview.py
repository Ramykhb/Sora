"""Bound dashboard encoding work independently of retained camera detail."""
import asyncio
from time import monotonic

from aiortc import VideoStreamTrack

from app.core.config import settings


class PreviewTrack(VideoStreamTrack):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.next_frame_at = None

    async def recv(self):
        while True:
            frame = await self.source.recv()
            received = monotonic()
            if self.next_frame_at is None or received >= self.next_frame_at:
                break
        interval = 1 / settings.stream_preview_max_fps
        if self.next_frame_at is None or self.next_frame_at < received - interval:
            self.next_frame_at = received
        self.next_frame_at += interval
        scale = min(1, settings.stream_preview_max_side / max(frame.width, frame.height))
        if scale < 1:
            # Even dimensions work with both VP8 and H.264. Reformat off the
            # event loop; preserve media timestamps rather than creating a new clock.
            width = max(2, int(frame.width * scale) // 2 * 2)
            height = max(2, int(frame.height * scale) // 2 * 2)
            frame = await asyncio.to_thread(frame.reformat, width=width, height=height)
        return frame

    def stop(self):
        self.source.stop()
        super().stop()
