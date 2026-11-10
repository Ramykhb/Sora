"""Configure aiortc's x264 context for the actual preview frame-rate budget."""
from fractions import Fraction

import av
from aiortc.codecs.h264 import H264Encoder

from app.core.config import settings


class PreviewH264Encoder(H264Encoder):
    def __init__(self):
        super().__init__()
        self.frame_rate = settings.stream_preview_max_fps

    def encode(self, frame, force_keyframe=False):
        # aiortc 1.x otherwise creates a hard-coded 30fps, Level 3.1 context.
        # Prepare the context here; retain its packetization, PLI and REMB logic.
        if (self.codec is None or self.codec.width != frame.width
                or self.codec.height != frame.height
                or abs(self.target_bitrate - self.codec.bit_rate) / self.codec.bit_rate > 0.1):
            self.buffer_data, self.buffer_pts = b"", None
            codec = av.CodecContext.create("libx264", "w")
            codec.width, codec.height = frame.width, frame.height
            codec.bit_rate = self.target_bitrate
            codec.pix_fmt = "yuv420p"
            codec.framerate = Fraction(self.frame_rate, 1)
            codec.time_base = Fraction(1, self.frame_rate)
            # Level 3.2 covers 720p60; larger test/source tracks need Level 4.2.
            level = "42" if max(frame.width, frame.height) > 1280 else (
                "32" if self.frame_rate > 30 else "31")
            codec.options = {"level": level, "preset": "veryfast", "tune": "zerolatency"}
            codec.profile = "Baseline"
            self.codec = codec
        return super().encode(frame, force_keyframe)
