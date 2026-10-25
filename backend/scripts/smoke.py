"""Run real model/storage/speech/optional WebRTC checks against a running backend."""

import argparse
import asyncio
from pathlib import Path
import httpx
from app.core.config import settings


async def check_webrtc(client, base, image_path):
    import cv2
    from aiortc import (
        RTCConfiguration,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
        VideoStreamTrack,
    )
    from av import VideoFrame

    response = await client.get(base + "/stream/config")
    response.raise_for_status()
    ice = response.json()["ice_servers"]
    peer = RTCPeerConnection(
        RTCConfiguration(iceServers=[RTCIceServer(**server) for server in ice])
    )
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("Test image cannot be decoded")

    height, width = image.shape[:2]
    scale = min(1.0, 1280 / max(width, height))
    if scale < 1:
        image = cv2.resize(image, (int(width * scale), int(height * scale)))

    class ImageTrack(VideoStreamTrack):
        async def recv(self):
            pts, time_base = await self.next_timestamp()
            frame = VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts, frame.time_base = pts, time_base
            return frame

    peer.addTrack(ImageTrack())
    try:
        await peer.setLocalDescription(await peer.createOffer())
        response = await client.post(
            base + "/stream/offer",
            json={"sdp": peer.localDescription.sdp, "type": peer.localDescription.type},
        )
        response.raise_for_status()
        await peer.setRemoteDescription(RTCSessionDescription(**response.json()))
        for _ in range(60):
            status = await client.get(base + "/stream/status")
            status.raise_for_status()
            if status.json().get("frames_received", 0) > 0:
                print("WebRTC video reached the backend")
                return
            await asyncio.sleep(0.5)
        raise RuntimeError("No WebRTC frames arrived; check ICE/TURN and network reachability")
    finally:
        await peer.close()
        await client.delete(base + "/stream")


async def run(args):
    async with httpx.AsyncClient(
        base_url=args.url.rstrip("/") + settings.api_prefix,
        headers={"X-API-Key": settings.api_key.get_secret_value()},
        timeout=300,
    ) as client:
        response = await client.post(
            "/sessions", json={"consent": True, "language": "en", "alerts_enabled": True}
        )
        response.raise_for_status()
        sid = response.json()["id"]
        base = f"/sessions/{sid}"
        try:
            response = await client.post(
                base + "/frames",
                files={"image": (args.image.name, args.image.read_bytes())},
                data={"force": "true"},
            )
            response.raise_for_status()
            frame = response.json()["frame"]
            print("Stored frame:", frame["id"], "warnings:", frame["processing_warnings"])
            failures = {"vision_unavailable", "embedding_unavailable"}
            if failures.intersection(frame["processing_warnings"]):
                raise RuntimeError("Model services did not complete image analysis")
            response = await client.get(
                base + "/frames/search", params={"q": "What does the sign say?"}
            )
            response.raise_for_status()
            assert response.json()["frames"], "No frame was retrieved"
            response = await client.post(
                base + "/questions",
                json={"question": "Describe what the camera saw.", "scope": "memory"},
            )
            response.raise_for_status()
            answer = response.json()
            print("Answer:", answer["answer"], "warnings:", answer["processing_warnings"])
            response = await client.get(base + f"/questions/{answer['id']}/audio")
            response.raise_for_status()
            assert response.content.startswith(b"RIFF"), "TTS did not return WAV"
            args.output.write_bytes(response.content)
            response = await client.post(
                "/speech/synthesis", json={"text": "What did the camera see?", "language": "en"}
            )
            response.raise_for_status()
            question_audio = args.audio.read_bytes() if args.audio else response.content
            response = await client.post(
                base + "/questions/audio",
                files={"audio": ("question.wav", question_audio)},
                data={"language": "en", "scope": "memory"},
            )
            response.raise_for_status()
            print("Recognized question:", response.json()["question"])
            response = await client.get(base + "/questions")
            response.raise_for_status()
            assert len(response.json()) == 2, "Question history was not persisted"
            if args.webrtc:
                await check_webrtc(client, base, args.image)
            response = await client.get("/metrics")
            response.raise_for_status()
            print("Metrics:", response.json())
            print("Real-service smoke flow completed. Spoken answer:", args.output)
        finally:
            response = await client.delete(base)
            response.raise_for_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--audio",
        type=Path,
        help="Optional recorded English question; otherwise use synthesized test speech",
    )
    parser.add_argument("--webrtc", action="store_true")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("/tmp/visual-assistant-answer.wav"))
    asyncio.run(run(parser.parse_args()))
