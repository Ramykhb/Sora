import asyncio
from fractions import Fraction

from aiortc import VideoStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame
import pytest

from app.services.streaming.relay import VideoRelay


def test_relay_absorbs_bursts_bounds_backlog_and_isolates_frame_storage():
    class Source(VideoStreamTrack):
        def __init__(self):
            super().__init__()
            self.queue = asyncio.Queue()
        async def recv(self):
            return await self.queue.get()

    async def exercise():
        source = Source()
        relay = VideoRelay(source)
        viewer = relay.subscribe(buffer_size=3)
        sampler = relay.subscribe(buffer_size=1)
        try:
            for index in range(5):
                frame = VideoFrame(64, 64, "yuv420p")
                frame.pts, frame.time_base = index * 3000, Fraction(1, 90000)
                source.queue.put_nowait(frame)
            await asyncio.sleep(0)
            assert viewer.queue.qsize() == 3 and sampler.queue.qsize() == 1
            frames = [await viewer.recv() for _ in range(3)]
            assert [frame.pts for frame in frames] == [6000, 9000, 12000]
            sample = await sampler.recv()
            assert sample.pts == frames[-1].pts and sample is not frames[-1]
            before = bytes(sample.planes[0])
            frames[-1].planes[0].update(bytes([127]) * frames[-1].planes[0].buffer_size)
            assert bytes(sample.planes[0]) == before
            waiting = asyncio.create_task(viewer.recv())
            await asyncio.sleep(0)
            viewer.stop()
            with pytest.raises(MediaStreamError):
                await waiting
            assert sampler.readyState == "live"
        finally:
            await relay.close()
        assert source.readyState == sampler.readyState == "ended"
        assert relay.task.done()

    asyncio.run(exercise())
