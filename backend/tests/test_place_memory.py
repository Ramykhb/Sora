import json
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import update

from app.core.config import settings
from app.db.models import QuestionAnswer
from app.db.models.frame import now
from app.services.ai import places
from test_api import create
from test_directions import route_result, transport


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(settings, "google_place_api_key", SecretStr("private-places"))
    monkeypatch.setattr(settings, "google_routes_api_key", SecretStr(""))
    monkeypatch.setattr(settings, "groq_api_key", SecretStr(""))


def ask(api, sid, question, location=None):
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": question, **({"location": location} if location is not None else {}),
    })
    assert result.status_code == 200
    return result.json()


def restaurant(place_id="original", name="Cedar Restaurant"):
    return {"places": [{"id": place_id, "displayName": {"text": name},
                        "location": {"latitude": .0036, "longitude": 0}}]}


@pytest.mark.parametrize("phrase", [
    "route to there", "route there", "take me there", "directions to it",
    "how do I get there?", "start a trip to that restaurant", "Let's go there",
    "itinéraire vers là-bas", "خذني هناك",
])
def test_reference_intents_are_place_trip_questions(phrase):
    assert places.is_destination_reference(phrase)
    assert places.is_trip_question(phrase) and places.is_place_question(phrase)


@pytest.mark.parametrize("phrase", ["route to McDonald's", "What is there?", "Is it safe there?", "What color is that restaurant?"])
def test_named_places_and_visual_references_do_not_reuse_destination(phrase):
    assert not places.is_destination_reference(phrase)


def test_followup_remembers_exact_place_across_requests_and_uses_new_origin(client, provider, monkeypatch):
    api, factory = client
    sid = create(api)
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "places.googleapis.com":
            assert request.url.path.endswith("places:searchNearby")
            return httpx.Response(200, json=restaurant())
        assert json.loads(request.content)["destination"] == {"placeId": "original"}
        assert json.loads(request.content)["origin"]["location"]["latLng"] == {"latitude": .001, "longitude": .002}
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    first = ask(api, sid, "What is the nearest restaurant?", {"latitude": 0, "longitude": 0})
    assert "Cedar Restaurant" in first["answer"]
    assert "place_context" not in first

    # An unrelated camera question must not replace the destination.
    ask(api, sid, "What is in front of me?")

    async def stored_context():
        async with factory() as db:
            row = await db.get(QuestionAnswer, UUID(first["id"]))
            return row.place_context

    context = api.portal.call(stored_context)
    assert context["place_id"] == "original" and context["name"] == "Cedar Restaurant"
    assert "origin" not in context
    for followup in ["route to there", "take me there"]:
        result = ask(api, sid, followup, {"latitude": .001, "longitude": .002})
        assert "Cedar Restaurant is approximately 500 m away on foot" in result["answer"]
        assert not result["uncertain"]
    assert calls == ["places.googleapis.com", "routes.googleapis.com", "routes.googleapis.com"]


def test_missing_memory_never_searches_for_literal_there_or_reuses_other_session(client, provider, monkeypatch):
    api, _ = client
    sid, other_sid = create(api), create(api)
    transport(monkeypatch, lambda _: httpx.Response(200, json=restaurant()))
    ask(api, sid, "nearest restaurant", {"latitude": 0, "longitude": 0})
    transport(monkeypatch, lambda _: pytest.fail("No provider call without a remembered destination"))
    result = ask(api, other_sid, "route to there", {"latitude": 0, "longitude": 0})
    assert result["processing_warnings"] == ["previous_destination_required"]
    assert "Which place" in result["answer"] and result["uncertain"]


def test_expired_destination_is_not_recalled(client, provider, monkeypatch):
    api, factory = client
    sid = create(api)
    transport(monkeypatch, lambda _: httpx.Response(200, json=restaurant()))
    first = ask(api, sid, "nearest restaurant", {"latitude": 0, "longitude": 0})

    async def expire():
        async with factory() as db:
            await db.execute(update(QuestionAnswer).where(QuestionAnswer.id == UUID(first["id"])).values(expires_at=now() - timedelta(seconds=1)))
            await db.commit()

    api.portal.call(expire)
    transport(monkeypatch, lambda _: pytest.fail("Expired destination must not be sent to Routes"))
    result = ask(api, sid, "take me there", {"latitude": 0, "longitude": 0})
    assert result["processing_warnings"] == ["previous_destination_required"]


def test_new_search_replaces_destination_and_failed_new_search_clears_ambiguous_reference(client, provider, monkeypatch):
    api, _ = client
    sid = create(api)
    destinations = []
    search_count = [0]

    def handler(request):
        if request.url.host == "places.googleapis.com":
            search_count[0] += 1
            result = restaurant("first") if search_count[0] == 1 else restaurant("second", "Second Cafe")
            if search_count[0] == 3:
                result = {"places": []}
            return httpx.Response(200, json=result)
        destinations.append(json.loads(request.content)["destination"]["placeId"])
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    location = {"latitude": 0, "longitude": 0}
    ask(api, sid, "nearest restaurant", location)
    ask(api, sid, "nearest cafe", location)
    result = ask(api, sid, "route there", location)
    assert "Second Cafe" in result["answer"] and destinations == ["second"]
    ask(api, sid, "nearest pharmacy", location)
    result = ask(api, sid, "route there", location)
    assert result["processing_warnings"] == ["previous_destination_required"]
    assert destinations == ["second"]


def test_followup_requires_fresh_origin_and_preserves_destination_for_retry(client, provider, monkeypatch):
    api, _ = client
    sid = create(api)
    transport(monkeypatch, lambda _: httpx.Response(200, json=restaurant()))
    ask(api, sid, "nearest restaurant", {"latitude": 0, "longitude": 0})
    transport(monkeypatch, lambda _: pytest.fail("Do not reuse old GPS"))
    assert ask(api, sid, "route there")["processing_warnings"] == ["location_required"]

    def handler(request):
        assert request.url.host == "routes.googleapis.com"
        assert json.loads(request.content)["destination"] == {"placeId": "original"}
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    result = ask(api, sid, "route there", {"latitude": .001, "longitude": 0})
    assert not result["uncertain"] and "Cedar Restaurant" in result["answer"]
