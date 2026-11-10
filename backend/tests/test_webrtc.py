import asyncio
from time import monotonic
from uuid import UUID
import numpy as np
import pytest
from app.core.config import settings
from app.services.streaming.session import accept_offer, accept_viewer_offer, close_viewer, streams
from test_api import create

pytest.importorskip("aiortc")
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame


@pytest.mark.parametrize("width,height", [(1280, 720), (1920, 1080)])
def test_webrtc_relays_continuous_video_and_samples_once_per_second(client, monkeypatch, width, height):
    api, _ = client
    sid = UUID(create(api))
    monkeypatch.setattr(settings, "sample_interval_seconds", 1.0)
    monkeypatch.setattr(settings, "turn_public_host", "")
    monkeypatch.setattr(settings, "ice_servers", [])
    token = api.headers["Authorization"].split(" ", 1)[1]
    import cv2
    from pathlib import Path
    image = cv2.resize(cv2.imread(str(Path(__file__).parent / "fixtures/astronaut.jpg")), (width, height))

    class Camera(VideoStreamTrack):
        async def recv(self):
            pts, time_base = await self.next_timestamp()
            frame = VideoFrame.from_ndarray(np.roll(image, (pts // 3000) * 4, axis=1), format="bgr24")
            frame.pts, frame.time_base = pts, time_base
            return frame

    async def exercise():
        publisher = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        viewer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        received_track = asyncio.get_running_loop().create_future()

        @viewer.on("track")
        def track(track):
            received_track.set_result(track)

        try:
            publisher.addTrack(Camera())
            await publisher.setLocalDescription(await publisher.createOffer())
            answer = await accept_offer(sid, publisher.localDescription.sdp, "offer", token)
            from aiortc.sdp import SessionDescription
            media = next(m for m in SessionDescription.parse(answer["sdp"]).media if m.kind == "video")
            assert media.rtp.codecs[0].mimeType.lower() == "video/h264"
            await publisher.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
            viewer.addTransceiver("video", direction="recvonly")
            await viewer.setLocalDescription(await viewer.createOffer())
            response = await accept_viewer_offer(sid, viewer.localDescription.sdp, "offer", token)
            media = next(m for m in SessionDescription.parse(response["sdp"]).media if m.kind == "video")
            assert media.rtp.codecs[0].mimeType.lower() == "video/h264"
            await viewer.setRemoteDescription(RTCSessionDescription(sdp=response["sdp"], type="answer"))
            track = await asyncio.wait_for(received_track, 5)
            first = await asyncio.wait_for(track.recv(), 5)
            assert first.width == 1280 and first.height == 720
            for _ in range(30):
                await asyncio.wait_for(track.recv(), 3)
            initial = streams.states[sid].sampled
            latest = cv2.imdecode(np.frombuffer(streams.states[sid].latest, np.uint8), 1)
            assert latest.shape[:2] == (height, width), "OCR sampling must retain source detail"
            count, start = 0, monotonic()
            while monotonic() - start < 5:
                await asyncio.wait_for(track.recv(), 3)
                count += 1
            state = streams.states[sid]
            measured_fps = count / (monotonic() - start)
            print(f"{width}×{height} source → 720p preview: {measured_fps:.1f} fps, input {streams.status(sid)['received_fps']}")
            assert measured_fps >= (27 if width == 1280 else 12), "720p capture must sustain approximately 30 fps"
            assert 4 <= state.sampled - initial <= 6
            if width == 1280:
                assert streams.status(sid)["received_fps"] >= 27
            assert state.sequence > state.sampled * 10
            await close_viewer(state, response["connection_id"])
            assert streams.states[sid] is state, "Closing a dashboard viewer must not stop the phone"
            assert publisher.connectionState == "connected"
            # Stale cleanup cannot close a replacement producer.
            await streams.stop(sid, expected=object())
            assert streams.states[sid] is state
        finally:
            await streams.stop(sid)
            await viewer.close()
            await publisher.close()

    api.portal.call(exercise)


def test_viewer_offer_requires_a_webrtc_producer(client):
    api, _ = client
    sid = create(api)
    response = api.post(f"/api/v1/sessions/{sid}/stream/viewer/offer", json={"type": "offer", "sdp": "invalid"})
    assert response.status_code == 409


def test_invalid_producer_offer_does_not_leave_a_stream(client):
    api, _ = client
    sid = create(api)
    response = api.post(f"/api/v1/sessions/{sid}/stream/offer", json={"type": "offer", "sdp": "invalid"})
    assert response.status_code == 422
    assert api.get(f"/api/v1/sessions/{sid}/stream/status").json()["streaming"] is False


def test_stream_config_issues_temporary_turn_credentials_not_the_shared_secret(client, monkeypatch):
    from pydantic import SecretStr
    import base64
    import hashlib
    import hmac

    api, _ = client
    sid = create(api)
    monkeypatch.setattr(settings, "turn_public_host", "192.168.0.104")
    monkeypatch.setattr(settings, "turn_shared_secret", SecretStr("test-relay-secret"))
    config = api.get(f"/api/v1/sessions/{sid}/stream/config").json()
    relay = config["ice_servers"][-1]
    expected = base64.b64encode(hmac.new(b"test-relay-secret", relay["username"].encode(), hashlib.sha1).digest()).decode()
    assert relay["credential"] == expected
    assert config["ice_transport_policy"] == "relay"
    assert "test-relay-secret" not in str(config)


@pytest.mark.parametrize("codec_name,encoder_name", [("vpx", "Vp8Encoder"), ("h264", "H264Encoder")])
def test_hd_encoder_budget_still_respects_congestion(monkeypatch, codec_name, encoder_name):
    from aiortc import codecs
    from app.services.streaming.quality import configure_video_encoders

    # Restore process-wide codec constants after exercising the compatibility shim.
    for module in (codecs.vpx, codecs.h264):
        monkeypatch.setattr(module, "MAX_BITRATE", module.MAX_BITRATE)
        monkeypatch.setattr(module, "DEFAULT_BITRATE", module.DEFAULT_BITRATE)
    monkeypatch.setattr(settings, "stream_video_max_bitrate", 6_000_000)
    configure_video_encoders()
    codec = getattr(codecs, codec_name)
    encoder = getattr(codec, encoder_name)()
    assert encoder.target_bitrate == 3_000_000
    encoder.target_bitrate = 5_000_000
    assert encoder.target_bitrate == 5_000_000, "HD must not hit aiortc's old codec ceiling"
    encoder.target_bitrate = 20_000_000
    assert encoder.target_bitrate == 6_000_000
    encoder.target_bitrate = 300_000
    assert encoder.target_bitrate == max(300_000, codec.MIN_BITRATE)
    assert encoder.target_bitrate < 1_500_000, "Congestion feedback must still reduce bandwidth"
