"""Process-wide aiortc encoder policy for bounded-resolution dashboard playback."""
from app.core.config import settings


def prefer_h264(peer):
    """Prefer the phone's hardware-friendly codec, retaining VP8 fallback."""
    from aiortc import RTCRtpSender

    codecs = RTCRtpSender.getCapabilities("video").codecs
    preferences = sorted(codecs, key=lambda codec: codec.mimeType.lower() != "video/h264")
    for transceiver in peer.getTransceivers():
        if transceiver.kind == "video":
            transceiver.setCodecPreferences(preferences)


def configure_video_encoders():
    from aiortc import codecs
    from aiortc.codecs import h264, vpx
    from app.services.streaming.h264 import PreviewH264Encoder

    # aiortc has no public sender bitrate API. Its encoders read these module
    # budgets at construction and when REMB arrives. Keep this compatibility
    # adjustment here, with real-encoder regression coverage for both codecs.
    # Preserve MIN_BITRATE: congestion feedback must still be able to lower rate.
    for codec in (vpx, h264):
        codec.MAX_BITRATE = settings.stream_video_max_bitrate
        codec.DEFAULT_BITRATE = min(3_000_000, codec.MAX_BITRATE)
    # Keep codec construction and advertised receive capabilities consistent
    # with 720p60 instead of aiortc's built-in 30fps / H.264 Level 3.1 defaults.
    codecs.H264Encoder = PreviewH264Encoder
    h264.H264Encoder = PreviewH264Encoder
    for codec in codecs.CODECS["video"]:
        if codec.mimeType.lower() in {"video/h264", "video/vp8"}:
            # libwebrtc's ~300kbps default takes too long to recover HD against
            # aiortc's receiver-side estimator. Hint only the starting rate;
            # REMB/congestion control can still reduce it after negotiation.
            codec.parameters["x-google-start-bitrate"] = str(
                min(3_000_000, settings.stream_video_max_bitrate) // 1000)
        if codec.mimeType.lower() == "video/h264":
            profile = codec.parameters["profile-level-id"]
            codec.parameters["profile-level-id"] = profile[:4] + (
                "20" if settings.stream_preview_max_fps > 30 else "1f")
