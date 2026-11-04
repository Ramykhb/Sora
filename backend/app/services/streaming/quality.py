"""Process-wide aiortc encoder policy for bounded-resolution dashboard playback."""
from app.core.config import settings


def configure_video_encoders():
    from aiortc.codecs import h264, vpx

    # aiortc has no public sender bitrate API. Its encoders read these module
    # budgets at construction and when REMB arrives. Keep this compatibility
    # adjustment here, with real-encoder regression coverage for both codecs.
    # Preserve MIN_BITRATE: congestion feedback must still be able to lower rate.
    for codec in (vpx, h264):
        codec.MAX_BITRATE = settings.stream_video_max_bitrate
        codec.DEFAULT_BITRATE = min(1_500_000, codec.MAX_BITRATE)
