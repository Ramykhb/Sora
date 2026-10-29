"""Real database authentication, token lifecycle and cross-user authorization tests."""

import asyncio
from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select, update
from starlette.websockets import WebSocketDisconnect
from app.core.auth import digest
from app.core.config import settings
from app.db.auth_models import AccountToken, AuthSession, User
from app.db.models import CaptureSession
from app.db.models.frame import now
from test_api import create, upload

PASSWORD = "long-enough-secret-password"


def account(api, email="person@example.com"):
    result = api.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Person"},
    )
    assert result.status_code == 201, result.text
    assert "password_hash" not in result.json()
    login = api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return login.json()


def headers(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def test_registration_validation_credentials_and_profile(client):
    api, factory = client
    pair = account(api, "Person@Example.com")
    assert pair["user"]["email"] == "person@example.com"
    assert pair["user"]["role"] == "user"
    assert api.get("/api/v1/auth/me", headers=headers(pair)).json()["email"] == "person@example.com"
    assert (
        api.patch(
            "/api/v1/auth/me", headers=headers(pair), json={"display_name": "New name"}
        ).json()["display_name"]
        == "New name"
    )
    assert (
        api.post(
            "/api/v1/auth/login", json={"email": "person@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        api.post(
            "/api/v1/auth/register",
            json={"email": "invalid", "password": PASSWORD, "display_name": "P"},
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "password": "short", "display_name": "P"},
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/api/v1/auth/register",
            json={"email": "person@example.com", "password": PASSWORD, "display_name": "P"},
        ).status_code
        == 409
    )
    assert (
        api.get(
            "/api/v1/sessions",
            headers={"Authorization": "", "X-API-Key": settings.api_key.get_secret_value()},
        ).status_code
        == 401
    )

    async def inspect():
        async with factory() as db:
            user = await db.scalar(select(User).where(User.email == "person@example.com"))
            assert user.password_hash.startswith("$argon2id$")
            row = await db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
            assert row.access_hash == digest(pair["access_token"])
            assert row.refresh_hash == digest(pair["refresh_token"])

    asyncio.run(inspect())


def test_refresh_rotation_replay_and_logout(client):
    api, _ = client
    first = account(api)
    response = api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert response.status_code == 200, response.text
    second = response.json()
    assert first["access_token"] != second["access_token"]
    assert api.get("/api/v1/auth/me", headers=headers(first)).status_code == 401
    assert api.get("/api/v1/auth/me", headers=headers(second)).status_code == 200
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code
        == 401
    )
    assert api.get("/api/v1/auth/me", headers=headers(second)).status_code == 401
    third = api.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    ).json()
    assert api.post("/api/v1/auth/logout", headers=headers(third)).status_code == 204
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": third["refresh_token"]}).status_code
        == 401
    )


def test_cross_user_http_websocket_and_metrics_isolation(client):
    api, _ = client
    owner, other = account(api), account(api, "other@example.com")
    original = dict(api.headers)
    api.headers.update(headers(owner))
    sid = create(api)
    frame = upload(api, sid)
    answer = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "What is visible?"}
    ).json()
    api.headers.update(headers(other))
    base = f"/api/v1/sessions/{sid}"
    for path in [
        "",
        "/frames",
        "/frames/search?q=EXIT",
        f"/frames/{frame['id']}",
        f"/frames/{frame['id']}/image",
        "/questions",
        f"/questions/{answer['id']}",
        f"/questions/{answer['id']}/audio",
        "/alerts",
        "/stream/config",
        "/stream/status",
        "/stream/live.mjpeg",
    ]:
        result = api.get(base + path)
        assert result.status_code == 404, (path, result.text)
    for method, path, data in [
        ("POST", "/questions", {"question": "What is visible?"}),
        ("PATCH", "", {"language": "fr"}),
        ("POST", "/close", {}),
        ("DELETE", "", None),
        ("DELETE", "/stream", None),
        ("POST", f"/questions/{answer['id']}/feedback", {"rating": "correct"}),
    ]:
        assert api.request(method, base + path, json=data).status_code == 404
    assert api.get("/api/v1/sessions").json() == []
    assert api.get("/api/v1/dashboard").json()["sessions"] == []
    assert api.get("/api/v1/metrics").json()["retained_frames"] == 0
    assert api.post("/api/v1/maintenance/cleanup").status_code == 403
    assert api.get("/ready").status_code == 403
    for path in ["/events", "/stream/frames"]:
        with api.websocket_connect(base + path) as socket:
            socket.send_json({"access_token": other["access_token"]})
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
    api.headers.clear()
    api.headers.update(original)
    assert api.get(base).status_code == 200  # administrators can inspect captures


def test_expired_tokens_logout_all_and_password_change(client):
    api, factory = client
    first = account(api)
    second = api.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    ).json()
    assert api.post("/api/v1/auth/logout-all", headers=headers(first)).status_code == 204
    for pair in [first, second]:
        assert api.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    pair = api.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    ).json()
    assert (
        api.post(
            "/api/v1/auth/change-password",
            headers=headers(pair),
            json={"current_password": "incorrect", "new_password": "new-long-password"},
        ).status_code
        == 401
    )
    assert (
        api.post(
            "/api/v1/auth/change-password",
            headers=headers(pair),
            json={"current_password": PASSWORD, "new_password": "new-long-password"},
        ).status_code
        == 204
    )
    assert api.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    assert (
        api.post(
            "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    pair = api.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": "new-long-password"}
    ).json()

    async def expire():
        async with factory() as db:
            await db.execute(
                update(AuthSession)
                .where(AuthSession.access_hash == digest(pair["access_token"]))
                .values(
                    access_expires_at=now() - timedelta(seconds=1),
                    expires_at=now() - timedelta(seconds=1),
                )
            )
            await db.commit()

    asyncio.run(expire())
    assert api.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code
        == 401
    )


def test_recovery_verification_single_use_and_revocation(client, monkeypatch):
    import app.services.authentication as service

    api, factory = client
    pair = account(api)
    sent = []

    async def email(address, token, purpose):
        sent.append((address, token, purpose))

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "sora@example.com")
    monkeypatch.setattr(service, "send_account_email", email)
    real = api.post("/api/v1/auth/forgot-password", json={"email": "person@example.com"})
    fake = api.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert real.status_code == fake.status_code == 202 and real.json() == fake.json()
    assert len(sent) == 1
    token = sent[-1][1]

    async def inspect():
        async with factory() as db:
            assert await db.get(AccountToken, digest(token)) is not None

    asyncio.run(inspect())
    reset = {"token": token, "new_password": "a-new-valid-password"}
    assert api.post("/api/v1/auth/reset-password", json=reset).status_code == 204
    assert api.post("/api/v1/auth/reset-password", json=reset).status_code == 400
    assert api.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    assert (
        api.post(
            "/api/v1/auth/login",
            json={"email": "person@example.com", "password": "a-new-valid-password"},
        ).status_code
        == 200
    )
    assert (
        api.post(
            "/api/v1/auth/resend-verification", json={"email": "person@example.com"}
        ).status_code
        == 202
    )
    assert api.post("/api/v1/auth/verify-email", json={"token": sent[-1][1]}).status_code == 204
    assert api.post("/api/v1/auth/verify-email", json={"token": sent[-1][1]}).status_code == 400
    login = api.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "a-new-valid-password"},
    ).json()
    assert login["user"]["email_verified"] is True


def test_admin_controls_deactivation_and_account_deletion(client):
    api, factory = client
    pair = account(api)
    uid = pair["user"]["id"]
    assert api.get("/api/v1/auth/users", headers=headers(pair)).status_code == 403
    assert api.patch("/api/v1/auth/users/" + uid, json={"is_active": False}).status_code == 200
    assert api.get("/api/v1/auth/me", headers=headers(pair)).status_code == 401
    assert (
        api.post(
            "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    api.patch("/api/v1/auth/users/" + uid, json={"is_active": True})
    pair = api.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    ).json()
    original = dict(api.headers)
    api.headers.update(headers(pair))
    sid = create(api)
    upload(api, sid)
    response = api.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD})
    assert response.status_code == 204, response.text
    assert api.get("/api/v1/auth/me").status_code == 401

    async def gone():
        async with factory() as db:
            assert await db.get(User, UUID(uid)) is None
            assert await db.get(CaptureSession, UUID(sid)) is None

    asyncio.run(gone())
    assert not any(settings.local_storage_dir.rglob("*.jpg"))
    api.headers.clear()
    api.headers.update(original)


def test_login_throttling_and_email_configuration(client):
    api, _ = client
    for _ in range(10):
        response = api.post(
            "/api/v1/auth/login", json={"email": "unknown@example.com", "password": "incorrect"}
        )
    assert response.status_code == 429  # fixture login consumes one IP attempt
    assert "Retry-After" in response.headers
    assert (
        api.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"}).status_code
        == 503
    )


def test_login_session_management_and_missing_refresh(client):
    api, _ = client
    first = account(api)
    second = account(api, "second@example.com")
    sessions = api.get("/api/v1/auth/sessions", headers=headers(first)).json()
    assert len(sessions) == 1 and sessions[0]["is_current"]
    assert not {"access_hash", "refresh_hash"}.intersection(sessions[0])
    sid = sessions[0]["id"]
    assert api.delete("/api/v1/auth/sessions/" + sid, headers=headers(second)).status_code == 404
    assert api.delete("/api/v1/auth/sessions/" + sid, headers=headers(first)).status_code == 204
    assert api.get("/api/v1/auth/me", headers=headers(first)).status_code == 401
    assert (
        api.post(
            "/api/v1/auth/refresh", json={"refresh_token": "invalid-but-long-enough-token"}
        ).status_code
        == 401
    )


def test_token_purpose_expiry_and_validation_redaction(client, monkeypatch):
    import app.services.authentication as service

    api, factory = client
    account(api)
    tokens = []

    async def email(address, token, purpose):
        tokens.append(token)

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "sora@example.com")
    monkeypatch.setattr(service, "send_account_email", email)
    api.post("/api/v1/auth/resend-verification", json={"email": "person@example.com"})
    assert (
        api.post(
            "/api/v1/auth/reset-password",
            json={"token": tokens[0], "new_password": "new-password-long"},
        ).status_code
        == 400
    )

    async def expire():
        async with factory() as db:
            await db.execute(update(AccountToken).values(expires_at=now() - timedelta(seconds=1)))
            await db.commit()

    asyncio.run(expire())
    assert api.post("/api/v1/auth/verify-email", json={"token": tokens[0]}).status_code == 400
    response = api.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "sensitive", "display_name": "P"},
    )
    assert response.status_code == 422 and "sensitive" not in response.text


def test_required_email_verification_and_closed_registration(client, monkeypatch):
    api, _ = client
    pair = account(api)
    monkeypatch.setattr(settings, "auth_require_verified_email", True)
    assert api.get("/api/v1/auth/me", headers=headers(pair)).status_code == 403
    assert (
        api.post(
            "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 403
    )
    monkeypatch.setattr(settings, "auth_registration_enabled", False)
    assert (
        api.post(
            "/api/v1/auth/register",
            json={"email": "closed@example.com", "password": PASSWORD, "display_name": "P"},
        ).status_code
        == 403
    )


def test_simultaneous_refresh_cannot_keep_two_valid_successors(client):
    from concurrent.futures import ThreadPoolExecutor

    api, _ = client
    pair = account(api)

    def refresh():
        return api.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: refresh(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 401]
    issued = next(r.json() for r in responses if r.status_code == 200)
    assert api.get("/api/v1/auth/me", headers=headers(issued)).status_code == 401


def test_logout_terminates_stream_and_revokes_event_subscription(client):
    api, _ = client
    pair = account(api)
    api.headers.update(headers(pair))
    sid = create(api)
    base = f"/api/v1/sessions/{sid}"
    with api.websocket_connect(base + "/events") as event_socket:
        event_socket.send_json({"access_token": pair["access_token"]})
        assert event_socket.receive_json()["type"] == "ready"
        with api.websocket_connect(base + "/stream/frames") as producer:
            producer.send_json({"access_token": pair["access_token"]})
            assert producer.receive_json()["type"] == "ready"
            assert event_socket.receive_json()["type"] == "stream_started"
            assert api.post("/api/v1/auth/logout").status_code == 204
            with pytest.raises(WebSocketDisconnect):
                event_socket.receive_json()


def test_dashboard_own_only_keeps_administrator_mobile_workspace_private(client):
    api, _ = client
    admin_headers = dict(api.headers)
    own_session = create(api)
    upload(api, own_session)
    other = account(api, "mobile-other@example.com")
    api.headers.update(headers(other))
    other_session = create(api)
    upload(api, other_session)
    api.headers.clear()
    api.headers.update(admin_headers)

    assert {item["id"] for item in api.get("/api/v1/sessions").json()} == {
        own_session,
        other_session,
    }
    assert [item["id"] for item in api.get("/api/v1/sessions?own_only=true").json()] == [
        own_session
    ]
    assert [
        item["session_id"]
        for item in api.get("/api/v1/dashboard?own_only=true").json()["sessions"]
    ] == [own_session]
    assert api.get("/api/v1/metrics").json()["retained_frames"] == 2
    own_metrics = api.get("/api/v1/metrics?own_only=true").json()
    assert own_metrics["retained_frames"] == 1
    assert own_metrics["pending_object_deletions"] is None

    api.headers.update(headers(other))
    for suffix in ("", "?own_only=true", "?own_only=false"):
        assert [item["id"] for item in api.get("/api/v1/sessions" + suffix).json()] == [
            other_session
        ]
        assert api.get("/api/v1/metrics" + suffix).json()["retained_frames"] == 1


def test_mobile_and_dashboard_logins_share_stream_frames_and_answers(client):
    from io import BytesIO

    from PIL import Image
    from test_api import image_bytes

    api, _ = client
    mobile = account(api, "shared-mobile@example.com")
    dashboard = api.post(
        "/api/v1/auth/login",
        json={"email": "shared-mobile@example.com", "password": PASSWORD},
    ).json()
    assert mobile["access_token"] != dashboard["access_token"]
    assert mobile["user"]["id"] == dashboard["user"]["id"]
    api.headers.update(headers(mobile))
    sid = create(api)
    path = f"/api/v1/sessions/{sid}"

    def receive_type(socket, event_type):
        for _ in range(10):
            message = socket.receive_json()
            if message["type"] == event_type:
                return message
        raise AssertionError(f"Expected {event_type}")

    with api.websocket_connect(path + "/events") as viewer:
        viewer.send_json({"access_token": dashboard["access_token"]})
        assert viewer.receive_json()["type"] == "ready"
        with api.websocket_connect(path + "/stream/frames") as producer:
            producer.send_json({"access_token": mobile["access_token"]})
            assert producer.receive_json()["type"] == "ready"
            assert receive_type(viewer, "stream_started")
            image = Image.open(BytesIO(image_bytes()))
            jpeg = BytesIO()
            image.save(jpeg, format="JPEG")
            producer.send_bytes(jpeg.getvalue())
            frame = receive_type(viewer, "frame_stored")["frame"]
            assert frame["session_id"] == sid
            assert frame["ocr_text"] == "EXIT"
            snapshot = api.get(
                "/api/v1/dashboard?own_only=true", headers=headers(dashboard)
            ).json()["sessions"]
            assert snapshot[0]["session_id"] == sid
            assert snapshot[0]["live"]["streaming"] is True
            result = api.post(
                path + "/questions",
                headers=headers(dashboard),
                json={"question": "What is visible?", "scope": "recent", "language": "en"},
            )
            assert result.status_code == 200, result.text
            event_answer = receive_type(viewer, "question_answered")["question"]
            assert event_answer["id"] == result.json()["id"]
            mobile_history = api.get(path + "/questions", headers=headers(mobile)).json()
            assert mobile_history[0]["id"] == event_answer["id"]
            patched = api.patch(
                path, headers=headers(dashboard), json={"language": "fr", "alerts_enabled": False}
            )
            assert patched.status_code == 200
            update = receive_type(viewer, "session_updated")["session"]
            assert update["language"] == "fr"
            assert update["alerts_enabled"] is False
            closed = api.post(path + "/close", headers=headers(dashboard))
            assert closed.status_code == 200
            assert receive_type(viewer, "session_updated")["session"]["status"] == "closed"
