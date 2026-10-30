import asyncio
from dataclasses import dataclass, field
import logging
from time import monotonic
from uuid import UUID, uuid4
from app.core.config import settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.services.events import events

logger = logging.getLogger(__name__)


@dataclass
class ViewerState:
    peer: object
    track: object
    auth_token: str


@dataclass
class LiveState:
    source: str
    auth_token: str | None = None
    latest: bytes | None = None
    last_received: float = field(default_factory=monotonic)
    last_sampled: float = float("-inf")
    sequence: int = 0
    sampled: int = 0
    stored: int = 0
    rejected: int = 0
    dropped: int = 0
    error: str | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1))
    updated: asyncio.Event = field(default_factory=asyncio.Event)
    worker: asyncio.Task | None = None
    peer: object | None = None
    readers: list = field(default_factory=list)
    connection_id: str = field(default_factory=lambda: str(uuid4()))
    relay: object | None = None
    video_track: object | None = None
    viewers: dict[str, ViewerState] = field(default_factory=dict)


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
        self.enqueue_sample(state, content, now())

    def enqueue_sample(self, state, content, timestamp):
        state.sampled += 1
        if state.queue.full():
            state.queue.get_nowait()
            state.dropped += 1
        state.queue.put_nowait((content, timestamp))

    async def consume(self, session_id, state):
        from app.services.frames.ingestion import ingest_bytes

        while True:
            content, timestamp = await state.queue.get()
            try:
                result = await ingest_bytes(
                    content, session_id, captured_at=timestamp,
                    defer_enrichment=settings.live_defer_enrichment,
                )
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
            "frames_sampled": state.sampled,
            "viewers": len(state.viewers),
            "sample_interval_seconds": settings.sample_interval_seconds,
            "frames_stored": state.stored,
            "frames_rejected": state.rejected,
            "frames_dropped": state.dropped,
            "last_frame_seconds_ago": monotonic() - state.last_received,
            "processing_error": state.error,
        }

    async def stop(self, session_id, expected=None):
        if expected is not None and self.states.get(session_id) is not expected:
            return
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
        for viewer_id in list(state.viewers):
            await close_viewer(state, viewer_id)
        if state.peer:
            await state.peer.close()
        events.publish(session_id, {"type": "stream_stopped"})

    async def close(self):
        await asyncio.gather(*(self.stop(sid) for sid in list(self.states)))

    async def reap_idle(self):
        from app.services.sessions import get_session

        while True:
            await asyncio.sleep(1)
            for session_id, state in list(self.states.items()):
                try:
                    await get_session(session_id, active=True)
                    if state.auth_token:
                        from app.core.auth import authenticate, check_ownership

                        principal = await authenticate(state.auth_token)
                        await check_ownership(session_id, principal.user)
                    expired = monotonic() - state.last_received > 60
                except Exception:
                    expired = True
                if expired:
                    await self.stop(session_id, expected=state)
                    continue
                for viewer_id, viewer in list(state.viewers.items()):
                    try:
                        from app.core.auth import authenticate, check_ownership

                        principal = await authenticate(viewer.auth_token)
                        await check_ownership(session_id, principal.user)
                    except Exception:
                        await close_viewer(state, viewer_id)


streams = Streams()


async def close_viewer(state, viewer_id):
    viewer = state.viewers.pop(viewer_id, None)
    if viewer:
        viewer.track.stop()
        await viewer.peer.close()


async def accept_offer(session_id, sdp, kind, auth_token=None):
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaRelay
    from aiortc.mediastreams import MediaStreamError
    from app.services.streaming.ice import rtc_configuration
    import cv2

    state = streams.start(session_id, "webrtc")
    state.auth_token = auth_token
    state.relay = MediaRelay()
    peer = RTCPeerConnection(configuration=rtc_configuration())
    state.peer = peer

    async def sample_video(track):
        try:
            while streams.states.get(session_id) is state:
                frame = await track.recv()
                received = monotonic()
                state.last_received = received
                state.sequence += 1
                if received - state.last_sampled < settings.sample_interval_seconds:
                    continue
                state.last_sampled = received
                captured_at = now()

                def encode():
                    image = frame.to_ndarray(format="bgr24")
                    height, width = image.shape[:2]
                    scale = min(1.0, settings.max_image_side / max(height, width))
                    if scale < 1:
                        image = cv2.resize(image, (int(width * scale), int(height * scale)))
                    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    return data.tobytes() if ok else None

                content = await asyncio.to_thread(encode)
                if content and streams.states.get(session_id) is state:
                    state.latest = content
                    state.updated.set()
                    streams.enqueue_sample(state, content, captured_at)
        except (MediaStreamError, asyncio.CancelledError):
            pass
        except Exception:
            logger.exception("WebRTC video sampling failed")
        finally:
            track.stop()
            await streams.stop(session_id, expected=state)

    @peer.on("track")
    def on_track(track):
        if track.kind == "video" and state.video_track is None:
            state.video_track = track
            sample_track = state.relay.subscribe(track, buffered=False)
            state.readers.append(asyncio.create_task(sample_video(sample_track)))
        else:
            track.stop()

    @peer.on("connectionstatechange")
    async def on_state():
        if peer.connectionState in {"closed", "failed"}:
            await streams.stop(session_id, expected=state)

    try:
        await peer.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=kind))
        if state.video_track is None:
            raise BackendError("Offer must include a sending video track", 422, "invalid_offer")
        answer = await peer.createAnswer()
        await peer.setLocalDescription(answer)
        return {"sdp": peer.localDescription.sdp, "type": peer.localDescription.type,
                "connection_id": state.connection_id}
    except BaseException:
        await streams.stop(session_id, expected=state)
        raise


async def accept_viewer_offer(session_id, sdp, kind, auth_token):
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from app.services.streaming.ice import rtc_configuration

    state = streams.states.get(session_id)
    if state is None or state.video_track is None or state.relay is None:
        raise BackendError("No WebRTC camera is streaming for this session", 409, "stream_unavailable")
    if len(state.viewers) >= settings.max_stream_viewers:
        raise BackendError("Viewer capacity reached", 429, "viewer_capacity")
    peer = RTCPeerConnection(configuration=rtc_configuration())
    track = state.relay.subscribe(state.video_track, buffered=False)
    viewer_id = str(uuid4())
    state.viewers[viewer_id] = ViewerState(peer=peer, track=track, auth_token=auth_token)

    @peer.on("connectionstatechange")
    async def on_state():
        if peer.connectionState in {"closed", "failed"}:
            await close_viewer(state, viewer_id)

    try:
        await peer.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=kind))
        if not any(t.kind == "video" and t.direction in {"sendrecv", "recvonly"}
                   for t in peer.getTransceivers()):
            raise BackendError("Viewer offer must receive video", 422, "invalid_offer")
        peer.addTrack(track)
        await peer.setLocalDescription(await peer.createAnswer())
        if streams.states.get(session_id) is not state:
            raise BackendError("Camera disconnected during negotiation", 409, "stream_unavailable")
        return {"sdp": peer.localDescription.sdp, "type": peer.localDescription.type,
                "connection_id": viewer_id}
    except BaseException:
        await close_viewer(state, viewer_id)
        raise
