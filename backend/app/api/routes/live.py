import asyncio
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from app.core.auth import valid_key
from app.core.config import settings
from app.core.errors import BackendError
from app.schemas import Offer
from app.services.events import events
from app.services.sessions import get_session
from app.services.streaming.session import accept_offer, streams

router = APIRouter()
ws_router = APIRouter()


@router.get("/config")
async def config(session_id: UUID):
    await get_session(session_id)
    return {
        "ice_servers": settings.ice_servers,
        "sample_interval_seconds": settings.sample_interval_seconds,
        "jpeg_websocket": f"{settings.api_prefix}/sessions/{session_id}/stream/frames",
        "events_websocket": f"{settings.api_prefix}/sessions/{session_id}/events",
    }


@router.post("/offer")
async def offer(session_id: UUID, request: Offer):
    await get_session(session_id, active=True)
    try:
        return await accept_offer(session_id, request.sdp, request.type)
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError(
            "Invalid WebRTC offer or media configuration", 422, "invalid_offer"
        ) from exc


@router.get("/status")
async def status(session_id: UUID):
    await get_session(session_id)
    return streams.status(session_id)


@router.delete("", status_code=204)
async def stop(session_id: UUID):
    await get_session(session_id)
    await streams.stop(session_id)
    return Response(status_code=204)


@router.get("/live.mjpeg")
async def live_view(session_id: UUID, request: Request):
    await get_session(session_id)
    state = streams.states.get(session_id)
    if state is None:
        raise HTTPException(409, "No producer is streaming for this session")

    async def generate():
        sequence = -1
        while streams.states.get(session_id) is state and not await request.is_disconnected():
            if state.latest and state.sequence != sequence:
                sequence = state.sequence
                content = state.latest
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(content)).encode()
                    + b"\r\n\r\n"
                    + content
                    + b"\r\n"
                )
            await asyncio.sleep(0.2)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def authenticate_socket(socket: WebSocket, session_id, active=False):
    origin = socket.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        await socket.close(code=1008)
        return False
    await socket.accept()
    try:
        message = await asyncio.wait_for(socket.receive_json(), timeout=5)
        if not isinstance(message, dict) or not valid_key(message.get("api_key")):
            await socket.close(code=1008, reason="Invalid API key")
            return False
        await get_session(session_id, active=active)
        return True
    except (ValueError, TypeError, asyncio.TimeoutError, WebSocketDisconnect, HTTPException):
        await socket.close(code=1008, reason="Authentication or session validation failed")
        return False


@ws_router.websocket("/sessions/{session_id}/stream/frames")
async def frame_socket(socket: WebSocket, session_id: UUID):
    if not await authenticate_socket(socket, session_id, active=True):
        return
    started = False
    try:
        streams.start(session_id, "jpeg-websocket")
        started = True
        await socket.send_json(
            {
                "type": "ready",
                "format": "binary JPEG",
                "sample_interval_seconds": settings.sample_interval_seconds,
            }
        )
        while session_id in streams.states:
            content = await asyncio.wait_for(socket.receive_bytes(), timeout=60)
            await get_session(session_id, active=True)
            streams.push(session_id, content)
    except WebSocketDisconnect:
        pass
    except (BackendError, HTTPException, asyncio.TimeoutError, KeyError) as exc:
        try:
            await socket.send_json({"type": "error", "code": getattr(exc, "code", "stream_closed")})
            await socket.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if started:
            await streams.stop(session_id)


@ws_router.websocket("/sessions/{session_id}/events")
async def event_socket(socket: WebSocket, session_id: UUID):
    if not await authenticate_socket(socket, session_id):
        return
    try:
        async with events.subscribe(session_id) as queue:
            await socket.send_json({"type": "ready", "stream": streams.status(session_id)})
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=10)
                    await get_session(session_id)
                    await socket.send_json(message)
                except asyncio.TimeoutError:
                    await get_session(session_id)
                    await socket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except (HTTPException, ValueError):
        await socket.close(code=1008, reason="Session unavailable or subscriber limit reached")
