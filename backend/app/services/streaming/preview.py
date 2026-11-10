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
        self.last_frame_at = None
        self.frames_forwarded = 0

    async def recv(self):
        while True:
            frame = await self.source.recv()
            # Network/decode arrival jitter is not the camera's frame rate.
            # At a 30fps limit, using wall time discards valid 30fps frames that
            # arrive a few milliseconds early, followed by gaps on late frames.
            received = frame.time if frame.time is not None else monotonic()
            if self.last_frame_at is not None and received < self.last_frame_at:
                self.next_frame_at = None
            self.last_frame_at = received
            if self.next_frame_at is None or received + 1e-6 >= self.next_frame_at:
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
        self.frames_forwarded += 1
        return frame

    def stop(self):
        self.source.stop()
        super().stop()
