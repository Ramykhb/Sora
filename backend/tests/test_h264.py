from fractions import Fraction
from copy import deepcopy

from aiortc.codecs.h264 import H264Decoder, H264PayloadDescriptor
from aiortc.jitterbuffer import JitterFrame
from av import VideoFrame
import pytest

from app.core.config import settings
from app.services.streaming.h264 import PreviewH264Encoder
from app.services.streaming.quality import configure_video_encoders


@pytest.mark.parametrize("fps,level", [(30, "1f"), (60, "20")])
def test_encoder_factory_and_sdp_capabilities_match_budget(monkeypatch, fps, level):
    from aiortc import codecs

    monkeypatch.setattr(settings, "stream_preview_max_fps", fps)
    monkeypatch.setitem(codecs.CODECS, "video", deepcopy(codecs.CODECS["video"]))
    configure_video_encoders()
    codec = next(codec for codec in codecs.CODECS["video"] if codec.mimeType == "video/H264")
    assert codec.parameters["profile-level-id"].endswith(level)
    assert codec.parameters["x-google-start-bitrate"] == "3000"
    encoder = codecs.get_encoder(codec)
    assert isinstance(encoder, PreviewH264Encoder)
    assert encoder.frame_rate == fps


@pytest.mark.parametrize("fps,level", [(30, 31), (60, 32)])
def test_portrait_h264_keeps_every_frame_and_timestamp_at_configured_rate(monkeypatch, fps, level):
    monkeypatch.setattr(settings, "stream_preview_max_fps", fps)
    encoder, decoder = PreviewH264Encoder(), H264Decoder()
    decoded_pts = []
    for index in range(12):
        frame = VideoFrame(720, 1280, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([128]) * plane.buffer_size)
        frame.pts, frame.time_base = index * (90000 // fps), Fraction(1, 90000)
        if index == 6:
            encoder.target_bitrate = 1_000_000
        payloads, timestamp = encoder.encode(frame)
        data = b"".join(H264PayloadDescriptor.parse(payload)[1] for payload in payloads)
        if index == 0:
            sps = data.index(b"\x00\x00\x00\x01\x67")
            assert data[sps + 7] == level
        decoded = decoder.decode(JitterFrame(data=data, timestamp=timestamp))
        assert all((item.width, item.height) == (720, 1280) for item in decoded)
        decoded_pts.extend(item.pts for item in decoded)
        assert encoder.codec.framerate == Fraction(fps, 1)
    assert decoded_pts == [index * (90000 // fps) for index in range(12)]
    assert encoder.codec.bit_rate == encoder.target_bitrate == 1_000_000
