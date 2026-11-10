"""Bounded decoded-video fanout that absorbs short network/decode bursts."""
import asyncio

from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame


class VideoSubscription(MediaStreamTrack):
    kind = "video"

    def __init__(self, relay, buffer_size):
        super().__init__()
        self.relay = relay
        self.queue = asyncio.Queue(maxsize=buffer_size)

    def deliver(self, frame):
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(frame)

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError
        frame = await self.queue.get()
        if frame is None:
            self.stop()
            raise MediaStreamError
        return frame

    def stop(self):
        if self.readyState == "live":
            super().stop()
            self.relay.subscribers.discard(self)
            while not self.queue.empty():
                self.queue.get_nowait()
            self.deliver(None)


class VideoRelay:
    def __init__(self, source):
        self.source = source
        self.subscribers = set()
        self.task = asyncio.create_task(self.run())

    def subscribe(self, buffer_size=3):
        subscription = VideoSubscription(self, buffer_size)
        self.subscribers.add(subscription)
        if self.task.done():
            subscription.stop()
        return subscription

    async def run(self):
        try:
            while True:
                frame = await self.source.recv()
                # PyAV caches a mutable reformatter on each frame. Sharing it
                # across the JPEG sampler and video encoders lets concurrent
                # conversions corrupt dimensions or crash FFmpeg. Give every
                # consumer its own frame and pixel storage, before threading.
                pixels = frame.to_ndarray(format="yuv420p")
                for subscription in self.subscribers:
                    copy = VideoFrame.from_ndarray(pixels, format="yuv420p")
                    copy.pts, copy.time_base = frame.pts, frame.time_base
                    copy.color_range, copy.colorspace = frame.color_range, frame.colorspace
                    subscription.deliver(copy)
        except MediaStreamError:
            pass
        finally:
            for subscription in list(self.subscribers):
                subscription.stop()

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.source.stop()
