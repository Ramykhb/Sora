import json
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
from app.db.models import SavedDestination
from app.services.ai import places
from app.services.ai.navigation_intent import route_target
from test_api import create
from test_auth import PASSWORD, account, headers
from test_directions import route_result, transport

BASE = "/api/v1/destinations"


def body(nickname="home", latitude=33.89, longitude=35.5):
    return {"nickname": nickname, "latitude": latitude, "longitude": longitude}


def save(api, **changes):
    result = api.post(BASE, json={**body(), **changes})
    assert result.status_code == 201, result.text
    return result.json()


def ask(api, sid, question, **extra):
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": question, "location": {"latitude": 33.8, "longitude": 35.4}, **extra,
    })
    assert result.status_code == 200, result.text
    return result.json()


def test_multiple_destinations_persist_edit_rename_delete(client):
    api, factory = client
    assert api.get(BASE).json() == []
    home = save(api, nickname="  Home  ")
    university = save(api, nickname="university", latitude=34, longitude=36)
    assert home["nickname"] == "Home" and "owner_id" not in home
    assert len(api.get(BASE).json()) == 2
    result = api.put(f'{BASE}/{home["id"]}', json=body("Family home", -33.9, -70.6))
    assert result.status_code == 200
    assert result.json()["latitude"] == -33.9 and result.json()["longitude"] == -70.6
    assert result.json()["nickname"] == "Family home"

    async def stored():
        async with factory() as db:
            return (await db.get(SavedDestination, UUID(home["id"]))).nickname

    assert api.portal.call(stored) == "Family home"
    assert api.delete(f'{BASE}/{home["id"]}').status_code == 204
    assert api.get(BASE).json() == [university]
    assert api.delete(f'{BASE}/{home["id"]}').status_code == 404


def test_normalized_nicknames_are_unique_per_account_and_conflicting_edits_leave_original(client):
    api, _ = client
    home = save(api, nickname="Home")
    university = save(api, nickname="university")
    assert api.post(BASE, json=body(" HOME ")).status_code == 409
    assert api.put(f'{BASE}/{university["id"]}', json=body("home")).status_code == 409
    assert {item["nickname"] for item in api.get(BASE).json()} == {"Home", "university"}
    assert api.put(f'{BASE}/{home["id"]}', json=body("home")).status_code == 200


@pytest.mark.parametrize("changes", [
    {"nickname": " "}, {"nickname": "..."}, {"nickname": "there"}, {"nickname": "it"},
    {"nickname": "x" * 81}, {"latitude": 91}, {"latitude": -91}, {"longitude": 181},
    {"longitude": -181}, {"latitude": "NaN"}, {"longitude": "Infinity"},
    {"owner_id": "00000000-0000-0000-0000-000000000000"},
])
def test_invalid_destination_is_rejected(client, changes):
    api, _ = client
    assert api.post(BASE, json={**body(), **changes}).status_code == 422
    assert api.get(BASE).json() == []


def test_authentication_and_private_crud_even_for_admins(client):
    api, _ = client
    admin_headers = dict(api.headers)
    person = account(api, "saved-owner@example.com")
    api.headers.update(headers(person))
    home = save(api)
    # Administrative capture access does not grant access to personal saved destinations.
    api.headers.update(admin_headers)
    assert api.get(BASE).json() == []
    assert api.put(f'{BASE}/{home["id"]}', json=body("Changed")).status_code == 404
    assert api.delete(f'{BASE}/{home["id"]}').status_code == 404
    save(api)  # The same nickname belongs independently to this account.
    api.headers.pop("Authorization")
    for method, path, payload in [("GET", BASE, None), ("POST", BASE, body()),
                                  ("PUT", f'{BASE}/{home["id"]}', body()), ("DELETE", f'{BASE}/{home["id"]}', None)]:
        assert api.request(method, path, **({"json": payload} if payload else {})).status_code == 401


def test_account_deletion_removes_saved_places(client):
    api, factory = client
    person = account(api, "saved-delete@example.com")
    api.headers.update(headers(person))
    save(api)
    assert api.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD}).status_code == 204

    async def remaining():
        async with factory() as db:
            return (await db.scalars(select(SavedDestination).where(SavedDestination.owner_id == UUID(person["user"]["id"])))).all()

    assert api.portal.call(remaining) == []


@pytest.mark.parametrize("question,nickname", [
    ("route home", "home"), ("Route to my home please", "my home"),
    ("navigate university", "university"), ("take me to Grandma's house", "Grandma's house"),
    ("please route to saved favorite cafe", "favorite cafe"),
    ("start a trip to university", "university"), ("go home", "home"),
    ("itinéraire vers université", "université"), ("خذني إلى الجامعة", "الجامعة"),
])
def test_saved_route_targets_are_extracted_without_ai(question, nickname):
    assert route_target(question).nickname == nickname
    assert places.is_trip_question(question)


@pytest.mark.parametrize("question", ["route home", "route to home", "route to my home", "navigate home", "go home", "route to saved home"])
def test_saved_route_skips_places_and_groq_uses_current_origin_and_supports_followup(client, monkeypatch, question):
    api, _ = client
    home = save(api)
    sid = create(api)
    # Saved-coordinate routing needs only a Routes key, not Places/Groq/Gemini.
    monkeypatch.setattr(settings, "google_place_api_key", SecretStr(""))
    monkeypatch.setattr(settings, "google_routes_api_key", SecretStr("private-routes"))
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("private-groq"))
    calls = []

    def handler(request):
        assert request.url.host == "routes.googleapis.com"
        payload = json.loads(request.content)
        assert payload["travelMode"] == "WALK"
        assert payload["origin"]["location"]["latLng"] == {"latitude": 33.8, "longitude": 35.4}
        assert payload["destination"] == {"location": {"latLng": {"latitude": home["latitude"], "longitude": home["longitude"]}}}
        calls.append(True)
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    result = ask(api, sid, question)
    assert "home is approximately 500 m away on foot" in result["answer"] and not result["uncertain"]
    assert not result["processing_warnings"]
    again = ask(api, sid, "route to there")
    assert "home is approximately 500 m away on foot" in again["answer"]
    assert len(calls) == 2


def test_edit_and_delete_are_reflected_by_next_route_and_never_fall_back_to_a_search(client, monkeypatch):
    api, _ = client
    home = save(api)
    sid = create(api)
    assert api.put(f'{BASE}/{home["id"]}', json=body("home", 1, 2)).status_code == 200

    def handler(request):
        assert request.url.host == "routes.googleapis.com"
        assert json.loads(request.content)["destination"]["location"]["latLng"] == {"latitude": 1, "longitude": 2}
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    assert not ask(api, sid, "route home")["uncertain"]
    assert api.delete(f'{BASE}/{home["id"]}').status_code == 204
    transport(monkeypatch, lambda _: pytest.fail("Deleted nickname must not trigger a place search"))
    result = ask(api, sid, "route home")
    assert result["processing_warnings"] == ["saved_destination_not_found"]
    assert "Settings" in result["answer"]


def test_saved_route_needs_current_gps_and_does_not_leak_between_accounts_or_sessions(client, monkeypatch):
    api, _ = client
    admin_headers = dict(api.headers)
    person = account(api, "saved-person@example.com")
    api.headers.update(headers(person))
    save(api)
    sid = create(api)
    transport(monkeypatch, lambda _: pytest.fail("No provider with missing GPS or private destination"))
    assert ask(api, sid, "route home", location=None)["processing_warnings"] == ["location_required"]
    api.headers.update(admin_headers)
    own_sid = create(api)
    assert ask(api, own_sid, "route home")["processing_warnings"] == ["saved_destination_not_found"]
    assert ask(api, sid, "route home")["processing_warnings"] == ["saved_destination_not_found"]


def test_saved_routes_work_from_visual_memory_screen_without_sending_images(client, monkeypatch):
    api, _ = client
    save(api, nickname="car park")  # A nickname is not a camera object question.
    sid = create(api)
    transport(monkeypatch, lambda request: httpx.Response(200, json=route_result()) if request.url.host == "routes.googleapis.com" else pytest.fail("Only Routes should be called"))
    assert not ask(api, sid, "route car park", scope="memory")["uncertain"]


def test_route_provider_failure_is_explicit_and_never_invents_directions(client, monkeypatch):
    api, _ = client
    save(api)
    sid = create(api)
    transport(monkeypatch, lambda _: httpx.Response(403, json={"error": {"message": "private-key"}}))
    result = ask(api, sid, "route home")
    assert result["uncertain"] and result["processing_warnings"] == ["routes_not_enabled"]
    assert "private-key" not in result["answer"] and "Turn" not in result["answer"]
