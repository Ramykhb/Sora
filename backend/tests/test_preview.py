import asyncio
from fractions import Fraction

from av import VideoFrame
import pytest

from app.services.streaming import preview


@pytest.mark.parametrize("width,height,expected", [(1920, 1080, (1280, 720)), (1080, 1920, (720, 1280)), (640, 480, (640, 480))])
def test_preview_preserves_timestamps_and_source_resolution(width, height, expected):
    frame = VideoFrame(width, height, "yuv420p")
    frame.pts, frame.time_base = 9000, Fraction(1, 90000)
    class Source:
        stopped = False
        async def recv(self):
            return frame
        def stop(self):
            self.stopped = True
    source = Source()
    track = preview.PreviewTrack(source)
    result = asyncio.run(track.recv())
    assert (result.width, result.height) == expected
    assert result.pts == 9000 and result.time_base == Fraction(1, 90000)
    assert (frame.width, frame.height) == (width, height)
    track.stop()
    assert source.stopped


def test_preview_drops_frames_without_accumulating_a_queue(monkeypatch):
    monkeypatch.setattr(preview.settings, "stream_preview_max_fps", 20)
    # A 30fps source should yield ~20fps, rather than rounding down to 15fps.
    clock = [0.0]
    monkeypatch.setattr(preview, "monotonic", lambda: clock[0])
    class Source:
        calls = 0
        async def recv(self):
            self.calls += 1
            clock[0] = self.calls / 30
            return VideoFrame(64, 64, "yuv420p")
        def stop(self):
            pass
    async def exercise():
        source = Source()
        track = preview.PreviewTrack(source)
        for _ in range(21):
            await track.recv()
        assert 29 <= source.calls <= 32
    asyncio.run(exercise())


@pytest.mark.parametrize("fps", [30, 60])
def test_preview_keeps_capture_fps_despite_decode_arrival_jitter(monkeypatch, fps):
    monkeypatch.setattr(preview.settings, "stream_preview_max_fps", fps)
    clock = [0.0]
    monkeypatch.setattr(preview, "monotonic", lambda: clock[0])
    class Source:
        calls = 0
        async def recv(self):
            self.calls += 1
            clock[0] = self.calls / fps + (0.012 if self.calls % 2 else -0.012)
            frame = VideoFrame(64, 64, "yuv420p")
            frame.pts, frame.time_base = self.calls * (90000 // fps), Fraction(1, 90000)
            return frame
        def stop(self):
            pass
    async def exercise():
        source = Source()
        track = preview.PreviewTrack(source)
        for _ in range(120):
            await track.recv()
        assert source.calls == 120
    asyncio.run(exercise())
