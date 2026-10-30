import asyncio
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from app.core.auth import authenticate, check_ownership
from app.core.config import settings
from app.core.errors import BackendError
from app.schemas import Offer
from app.services.events import events
from app.services.sessions import get_session
from app.services.streaming.session import accept_offer, accept_viewer_offer, close_viewer, streams
from app.services.streaming.ice import ice_servers

router = APIRouter()
ws_router = APIRouter()


@router.get("/config")
async def config(session_id: UUID):
    await get_session(session_id)
    return {
        "ice_servers": ice_servers(),
        "ice_transport_policy": "relay" if settings.turn_public_host and settings.turn_shared_secret.get_secret_value() else "all",
        "sample_interval_seconds": settings.sample_interval_seconds,
        "jpeg_websocket": f"{settings.api_prefix}/sessions/{session_id}/stream/frames",
        "events_websocket": f"{settings.api_prefix}/sessions/{session_id}/events",
    }


@router.post("/offer")
async def offer(session_id: UUID, request: Offer, http_request: Request):
    await get_session(session_id, active=True)
    try:
        return await accept_offer(
            session_id, request.sdp, request.type,
            http_request.headers["authorization"].split(" ", 1)[1],
        )
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError(
            "Invalid WebRTC offer or media configuration", 422, "invalid_offer"
        ) from exc


@router.post("/viewer/offer")
async def viewer_offer(session_id: UUID, request: Offer, http_request: Request):
    await get_session(session_id, active=True)
    try:
        return await accept_viewer_offer(
            session_id, request.sdp, request.type,
            http_request.headers["authorization"].split(" ", 1)[1],
        )
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError("Invalid WebRTC viewer offer", 422, "invalid_offer") from exc


@router.post("/connections/{connection_id}/refresh", status_code=204)
async def refresh_connection(session_id: UUID, connection_id: str, request: Request):
    state = streams.states.get(session_id)
    if state is None:
        raise HTTPException(409, "Camera is no longer connected")
    token = request.headers["authorization"].split(" ", 1)[1]
    if connection_id == state.connection_id:
        state.auth_token = token
    elif connection_id in state.viewers:
        state.viewers[connection_id].auth_token = token
    else:
        raise HTTPException(404, "Connection not found")
    return Response(status_code=204)


@router.delete("/connections/{connection_id}", status_code=204)
async def close_connection(session_id: UUID, connection_id: str):
    state = streams.states.get(session_id)
    if state is not None:
        if connection_id == state.connection_id:
            await streams.stop(session_id, expected=state)
        else:
            await close_viewer(state, connection_id)
    return Response(status_code=204)


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
        from time import monotonic

        checked_at = 0
        while streams.states.get(session_id) is state and not await request.is_disconnected():
            if monotonic() - checked_at > 1:
                try:
                    principal = await authenticate(
                        request.headers.get("authorization", "").split(" ", 1)[-1]
                    )
                    await check_ownership(session_id, principal.user)
                except HTTPException:
                    return
                checked_at = monotonic()
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


@router.get("/preview.jpg")
async def preview_image(session_id: UUID):
    await get_session(session_id)
    state = streams.states.get(session_id)
    if state is None:
        raise HTTPException(409, "No producer is streaming for this session")
    if state.latest is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    return Response(
        content=state.latest,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


async def authenticate_socket(socket: WebSocket, session_id, active=False):
    origin = socket.headers.get("origin")
    # Native WebSocket clients send the API's own HTTP(S) origin, including
    # its LAN address on a physical phone. Accept same-origin connections as
    # well as explicitly configured cross-origin browser clients.
    scheme = "https" if socket.url.scheme == "wss" else "http"
    same_origin = f"{scheme}://{socket.url.netloc}"
    if origin and origin not in settings.cors_origins and origin != same_origin:
        await socket.close(code=1008)
        return False
    await socket.accept()
    try:
        message = await asyncio.wait_for(socket.receive_json(), timeout=5)
        if not isinstance(message, dict):
            raise ValueError("Authentication message required")
        principal = await authenticate(message.get("access_token"))
        await check_ownership(session_id, principal.user)
        socket.scope["auth_token"] = message["access_token"]
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
        streams.start(session_id, "jpeg-websocket").auth_token = socket.scope["auth_token"]
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
            principal = await authenticate(socket.scope["auth_token"])
            await check_ownership(session_id, principal.user)
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
                    principal = await authenticate(socket.scope["auth_token"])
                    await check_ownership(session_id, principal.user)
                    await get_session(session_id)
                    await socket.send_json(message)
                except asyncio.TimeoutError:
                    principal = await authenticate(socket.scope["auth_token"])
                    await check_ownership(session_id, principal.user)
                    await get_session(session_id)
                    await socket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except (HTTPException, ValueError):
        await socket.close(code=1008, reason="Session unavailable or subscriber limit reached")
