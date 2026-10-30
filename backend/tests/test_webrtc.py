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


def test_webrtc_relays_continuous_video_and_samples_once_per_second(client, monkeypatch):
    api, _ = client
    sid = UUID(create(api))
    monkeypatch.setattr(settings, "sample_interval_seconds", 1.0)
    monkeypatch.setattr(settings, "turn_public_host", "")
    monkeypatch.setattr(settings, "ice_servers", [])
    token = api.headers["Authorization"].split(" ", 1)[1]

    class Camera(VideoStreamTrack):
        async def recv(self):
            pts, time_base = await self.next_timestamp()
            pixels = np.indices((240, 320)).sum(axis=0) % 2 * 200 + 30
            frame = VideoFrame.from_ndarray(np.repeat(pixels[:, :, None], 3, axis=2).astype(np.uint8), format="rgb24")
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
            await publisher.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
            viewer.addTransceiver("video", direction="recvonly")
            await viewer.setLocalDescription(await viewer.createOffer())
            response = await accept_viewer_offer(sid, viewer.localDescription.sdp, "offer", token)
            await viewer.setRemoteDescription(RTCSessionDescription(sdp=response["sdp"], type="answer"))
            track = await asyncio.wait_for(received_track, 5)
            first = await asyncio.wait_for(track.recv(), 5)
            assert first.width == 320 and first.height == 240
            initial = streams.states[sid].sampled
            count, start = 1, monotonic()
            while monotonic() - start < 2.2:
                await asyncio.wait_for(track.recv(), 3)
                count += 1
            state = streams.states[sid]
            assert count > 20, "Viewer must receive continuous video, not one image per sample"
            assert 2 <= state.sampled - initial <= 3
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
