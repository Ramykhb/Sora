import asyncio
from dataclasses import dataclass, field
import logging
from time import monotonic
from uuid import UUID
from app.core.config import settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.services.events import events

logger = logging.getLogger(__name__)


@dataclass
class LiveState:
    source: str
    latest: bytes | None = None
    last_received: float = field(default_factory=monotonic)
    last_sampled: float = 0
    sequence: int = 0
    stored: int = 0
    rejected: int = 0
    dropped: int = 0
    error: str | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1))
    updated: asyncio.Event = field(default_factory=asyncio.Event)
    worker: asyncio.Task | None = None
    peer: object | None = None
    readers: list = field(default_factory=list)


class Streams:
    def __init__(self):
        self.states: dict[UUID, LiveState] = {}

    def start(self, session_id, source):
        if session_id in self.states:
            raise BackendError(
                "A producer is already connected to this session", 409, "stream_exists"
            )
        if len(self.states) >= settings.max_live_sessions:
            raise BackendError("Live session capacity reached", 429, "stream_capacity")
        state = LiveState(source=source)
        self.states[session_id] = state
        state.worker = asyncio.create_task(self.consume(session_id, state))
        events.publish(session_id, {"type": "stream_started", "source": source})
        return state

    def push(self, session_id, content):
        state = self.states.get(session_id)
        if state is None:
            return
        if (
            not content.startswith(b"\xff\xd8")
            or len(content) > settings.max_upload_mb * 1024 * 1024
        ):
            raise BackendError(
                "Stream frames must be JPEG within upload limit", 422, "invalid_frame"
            )
        state.latest, state.last_received = content, monotonic()
        state.sequence += 1
        state.updated.set()
        if monotonic() - state.last_sampled < settings.sample_interval_seconds:
            return
        state.last_sampled = monotonic()
        if state.queue.full():
            state.queue.get_nowait()
            state.dropped += 1
        state.queue.put_nowait((content, now()))

    async def consume(self, session_id, state):
        from app.services.frames.ingestion import ingest_bytes

        while True:
            content, timestamp = await state.queue.get()
            try:
                result = await ingest_bytes(content, session_id, captured_at=timestamp)
                if result.status == "stored":
                    state.stored += 1
                else:
                    state.rejected += 1
                state.error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.error = exc.code if isinstance(exc, BackendError) else "processing_failed"
                logger.exception("Live frame processing failed")
                events.publish(session_id, {"type": "processing_error", "code": state.error})
            finally:
                state.queue.task_done()

    def status(self, session_id):
        state = self.states.get(session_id)
        if state is None:
            return {"streaming": False}
        return {
            "streaming": True,
            "source": state.source,
            "frames_received": state.sequence,
            "frames_stored": state.stored,
            "frames_rejected": state.rejected,
            "frames_dropped": state.dropped,
            "last_frame_seconds_ago": monotonic() - state.last_received,
            "processing_error": state.error,
        }

    async def stop(self, session_id):
        state = self.states.pop(session_id, None)
        if state is None:
            return
        state.updated.set()
        tasks = [
            task
            for task in [state.worker, *state.readers]
            if task and task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if state.peer:
            await state.peer.close()
        events.publish(session_id, {"type": "stream_stopped"})

    async def close(self):
        await asyncio.gather(*(self.stop(sid) for sid in list(self.states)))

    async def reap_idle(self):
        from app.services.sessions import get_session

        while True:
            await asyncio.sleep(10)
            for session_id, state in list(self.states.items()):
                try:
                    await get_session(session_id, active=True)
                    expired = monotonic() - state.last_received > 60
                except Exception:
                    expired = True
                if expired:
                    await self.stop(session_id)


streams = Streams()


async def accept_offer(session_id, sdp, kind):
    try:
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        from aiortc.mediastreams import MediaStreamError
    except ImportError as exc:
        raise BackendError("WebRTC runtime is not installed", 503, "media_unavailable") from exc
    import cv2

    state = streams.start(session_id, "webrtc")
    peer = RTCPeerConnection(
        configuration=RTCConfiguration(
            iceServers=[RTCIceServer(**item) for item in settings.ice_servers]
        )
    )
    state.peer = peer

    async def read_video(track):
        last_preview = 0
        try:
            while True:
                frame = await track.recv()
                if monotonic() - last_preview < 0.2:
                    continue
                last_preview = monotonic()

                def encode():
                    image = frame.to_ndarray(format="bgr24")
                    height, width = image.shape[:2]
                    scale = min(1.0, settings.max_image_side / max(height, width))
                    if scale < 1:
                        image = cv2.resize(image, (int(width * scale), int(height * scale)))
                    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    return data.tobytes() if ok else None

                content = await asyncio.to_thread(encode)
                if content:
                    streams.push(session_id, content)
        except (MediaStreamError, asyncio.CancelledError):
            pass
        finally:
            await streams.stop(session_id)

    @peer.on("track")
    def on_track(track):
        if track.kind == "video":
            state.readers.append(asyncio.create_task(read_video(track)))
        else:
            track.stop()

    @peer.on("connectionstatechange")
    async def on_state():
        if peer.connectionState in {"closed", "failed"}:
            await streams.stop(session_id)

    try:
        await peer.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=kind))
        if not any(transceiver.kind == "video" for transceiver in peer.getTransceivers()):
            raise BackendError("Offer must include a video track", 422, "invalid_offer")
        answer = await peer.createAnswer()
        await peer.setLocalDescription(answer)
        return {"sdp": peer.localDescription.sdp, "type": peer.localDescription.type}
    except BaseException:
        await streams.stop(session_id)
        raise
