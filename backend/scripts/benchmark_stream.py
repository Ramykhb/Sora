"""Measure real 720p publish → API → viewer throughput using a temporary account."""
import argparse
import asyncio
import json
from pathlib import Path
import secrets
from fractions import Fraction
from time import monotonic

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
import cv2
import httpx
import numpy as np

from app.services.streaming.quality import configure_video_encoders


def relay_sdp(sdp):
    lines = sdp.splitlines()
    if not any(line.startswith("a=candidate:") and " typ relay" in line for line in lines):
        raise RuntimeError("No TURN candidate: check the advertised relay address and ports")
    return "\r\n".join(line for line in lines if not line.startswith("a=candidate:")
                       or " typ relay" in line) + "\r\n"


async def benchmark(args):
    configure_video_encoders()
    if args.image:
        pixels = cv2.imread(str(args.image))
        if pixels is None:
            raise ValueError("Cannot decode benchmark image")
        pixels = cv2.resize(pixels, (1280, 720))
    else:
        y, x = np.indices((720, 1280))
        pixels = np.stack(((x // 5) % 256, (y // 3) % 256,
                           ((x + y) // 6) % 256), axis=2).astype(np.uint8)

    class Camera(VideoStreamTrack):
        def __init__(self):
            super().__init__()
            self.started = None
            self.index = 0

        async def recv(self):
            if self.started is None:
                self.started = monotonic()
            await asyncio.sleep(max(0, self.started + self.index / args.fps - monotonic()))
            frame = VideoFrame.from_ndarray(np.roll(pixels, self.index * 3, axis=1), format="bgr24")
            frame.pts, frame.time_base = round(self.index * 90000 / args.fps), Fraction(1, 90000)
            self.index += 1
            return frame

    password = secrets.token_urlsafe(32)
    email = f"stream-benchmark-{secrets.token_hex(8)}@example.test"
    async with httpx.AsyncClient(base_url=args.url.rstrip("/") + "/api/v1", timeout=30) as api:
        response = await api.post("/auth/register", json={
            "email": email, "password": password, "display_name": "Temporary stream benchmark",
        })
        response.raise_for_status()
        publisher = viewer = None
        try:
            response = await api.post("/auth/login", json={"email": email, "password": password})
            response.raise_for_status()
            api.headers["Authorization"] = "Bearer " + response.json()["access_token"]
            response = await api.post("/sessions", json={
                "consent": True, "language": "en", "alerts_enabled": False,
            })
            response.raise_for_status()
            path = f"/sessions/{response.json()['id']}/stream"
            response = await api.get(path + "/config")
            response.raise_for_status()
            config = RTCConfiguration(iceServers=[RTCIceServer(**server)
                                                 for server in response.json()["ice_servers"]])
            publisher, viewer = RTCPeerConnection(config), RTCPeerConnection(config)

            async def negotiate(peer, endpoint):
                await peer.setLocalDescription(await peer.createOffer())
                sdp = peer.localDescription.sdp
                response = await api.post(path + endpoint, json={
                    "type": "offer", "sdp": relay_sdp(sdp) if args.relay_only else sdp,
                })
                response.raise_for_status()
                sdp = response.json()["sdp"]
                await peer.setRemoteDescription(RTCSessionDescription(
                    sdp=relay_sdp(sdp) if args.relay_only else sdp, type="answer",
                ))

            publisher.addTrack(Camera())
            await negotiate(publisher, "/offer")
            got_track = asyncio.get_running_loop().create_future()

            @viewer.on("track")
            def on_track(track):
                if not got_track.done():
                    got_track.set_result(track)

            viewer.addTransceiver("video", direction="recvonly")
            await negotiate(viewer, "/viewer/offer")
            track = await asyncio.wait_for(got_track, 15)
            # Allow codec startup, initial keyframes and congestion feedback to settle.
            for _ in range(args.fps * 2):
                await asyncio.wait_for(track.recv(), 10)
            results = []
            for _ in range(3):
                count, start = 0, monotonic()
                while monotonic() - start < args.seconds / 3:
                    frame = await asyncio.wait_for(track.recv(), 10)
                    if (frame.width, frame.height) != (1280, 720):
                        raise RuntimeError(f"Unexpected resolution: {frame.width}×{frame.height}")
                    count += 1
                fps = count / (monotonic() - start)
                response = await api.get(path + "/status")
                response.raise_for_status()
                result = {"playback_fps": round(fps, 2), "resolution": "1280×720",
                          "received_fps": response.json().get("received_fps"),
                          "target_fps": args.fps,
                          "relay_only": args.relay_only}
                results.append(result)
                print(json.dumps(result), flush=True)
            if min(result["playback_fps"] for result in results) < args.fps * 0.9:
                raise RuntimeError(f"720p playback did not sustain approximately {args.fps} fps")
        finally:
            if viewer:
                await viewer.close()
            if publisher:
                await publisher.close()
            if "Authorization" in api.headers:
                response = await api.request("DELETE", "/auth/me", json={"password": password})
                response.raise_for_status()
                print("Temporary benchmark account and sessions removed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--image", type=Path, help="Optional local image to pan across instead of a generated pattern")
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--fps", type=int, choices=[30, 60], default=60)
    parser.add_argument("--relay-only", action="store_true", help="Require TURN for both media legs")
    args = parser.parse_args()
    if args.seconds < 9:
        parser.error("--seconds must be at least 9")
    asyncio.run(benchmark(args))
