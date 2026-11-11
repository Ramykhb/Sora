import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.schemas import QuestionRequest
from app.services.ai import directions, places
from test_api import create

HTTP_CLIENT = httpx.AsyncClient


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(settings, "google_place_api_key", SecretStr("private-places"))
    monkeypatch.setattr(settings, "google_routes_api_key", SecretStr(""))
    monkeypatch.setattr(settings, "groq_api_key", SecretStr(""))


def transport(monkeypatch, handler):
    monkeypatch.setattr(directions.httpx, "AsyncClient", lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(handler), **kw))


def place_results():
    return {"places": [
        {"id": "far", "displayName": {"text": "McDonald's Far"}, "location": {"latitude": .01, "longitude": 0}},
        {"id": "nearest", "displayName": {"text": "McDonald's Hamra"}, "location": {"latitude": .0036, "longitude": 0}},
        {"id": "unrelated", "displayName": {"text": "Mc Donna"}, "location": {"latitude": .001, "longitude": 0}},
    ]}


def route_result():
    return {"routes": [{"distanceMeters": 500, "legs": [{"steps": [
        {"distanceMeters": 100, "navigationInstruction": {"instructions": "Head north on First Street"}},
        {"distanceMeters": 200, "navigationInstruction": {"instructions": "Turn right onto Second Street"}},
        {"distanceMeters": 200, "navigationInstruction": {"instructions": "Turn left onto Third Street"}},
        {"navigationInstruction": {"instructions": "Your destination is on the right"}},
    ]}]}]}


@pytest.mark.parametrize("question", [
    "start trip to the nearest mcdonalds", "start a walking route to McDonald's",
    "give me directions to mcdonalds", "navigate me to the nearest McDonald's",
    "route to McDonald's", "how do I get to McDonald's?",
    "itinéraire vers le McDonald's le plus proche", "ابدأ رحلة إلى أقرب ماكدونالدز",
])
def test_trip_intent(question):
    assert places.is_trip_question(question)
    assert places.is_place_question(question)


@pytest.mark.parametrize("question", ["What is the nearest McDonald's?", "How far is Starbucks?", "Is it safe to walk?", "Is the route clear?"])
def test_lookup_and_visual_questions_are_not_trip_requests(question):
    assert not places.is_trip_question(question)


def test_route_request_uses_nearest_matching_place_walking_and_provider_steps(client, provider, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        body = json.loads(request.content)
        assert "private-places" not in str(request.url)
        assert request.headers["x-goog-api-key"] == "private-places"
        if request.url.host == "places.googleapis.com":
            assert body["textQuery"] == "McDonald's"
            assert "places.id" in request.headers["x-goog-fieldmask"]
            return httpx.Response(200, json=place_results())
        assert request.url.host == "routes.googleapis.com"
        assert request.url.path == "/directions/v2:computeRoutes"
        assert body["travelMode"] == "WALK" and body["units"] == "METRIC"
        assert body["origin"] == {"location": {"latLng": {"latitude": 0, "longitude": 0}}}
        assert body["destination"] == {"placeId": "nearest"}
        assert "routes.legs.steps.navigationInstruction" in request.headers["x-goog-fieldmask"]
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    api, _ = client
    sid = create(api)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "Start a trip to the nearest McDonald's", "location": {"latitude": 0, "longitude": 0},
    })
    assert result.status_code == 200
    answer = result.json()
    assert "McDonald's Hamra is approximately 500 m away on foot" in answer["answer"]
    assert "1. Head north on First Street (100 m)." in answer["answer"]
    assert "2. Turn right onto Second Street (200 m)." in answer["answer"]
    assert "3. Turn left onto Third Street (200 m)." in answer["answer"]
    assert "4. Your destination is on the right." in answer["answer"]
    assert "missing sidewalks" in answer["answer"]
    assert not answer["uncertain"] and not answer["evidence_frame_ids"]
    assert calls == ["places.googleapis.com", "routes.googleapis.com"]
    saved = api.get(f"/api/v1/sessions/{sid}/questions").json()[0]
    assert saved["answer"] == answer["answer"]


@pytest.mark.parametrize("status,payload,code", [
    (403, {"error": {"message": "private-places"}}, "routes_not_enabled"),
    (429, {"error": {"message": "private-places"}}, "routes_unavailable"),
    (200, {"routes": []}, "routes_no_results"),
    (200, {"routes": [{"distanceMeters": 500, "legs": [{"steps": [{"distanceMeters": 100}]}]}]}, "routes_unavailable"),
])
def test_route_failures_do_not_replace_distance_with_invented_directions(provider, monkeypatch, status, payload, code):
    def handler(request):
        if request.url.host == "places.googleapis.com":
            return httpx.Response(200, json=place_results())
        return httpx.Response(status, json=payload)

    transport(monkeypatch, handler)
    answer, uncertain, evidence, warnings = asyncio.run(places.answer_nearby(QuestionRequest(
        question="start trip to closest mcdonalds", location={"latitude": 0, "longitude": 0},
    ), "en"))
    assert "400 m" in answer and "straight-line" in answer
    assert directions.MESSAGES[code]["en"] in answer
    assert "private-places" not in answer and "Turn" not in answer
    assert uncertain and not evidence and warnings == [code]


def test_route_timeout_is_sanitized(provider, monkeypatch):
    def handler(request):
        if request.url.host == "places.googleapis.com":
            return httpx.Response(200, json=place_results())
        raise httpx.ReadTimeout("private-places", request=request)

    transport(monkeypatch, handler)
    result = asyncio.run(places.answer_nearby(QuestionRequest(
        question="start trip to nearest mcdonalds", location={"latitude": 0, "longitude": 0},
    ), "en"))
    assert result[3] == ["routes_unavailable"] and "private-places" not in result[0]


def test_trip_missing_origin_or_destination_makes_no_provider_calls(provider, monkeypatch):
    transport(monkeypatch, lambda _: pytest.fail("No request without destination and origin"))
    result = asyncio.run(places.answer_nearby(QuestionRequest(question="start trip to McDonald's"), "en"))
    assert result[3] == ["location_required"]
    result = asyncio.run(places.answer_nearby(QuestionRequest(question="start a trip"), "en"))
    assert result[3] == ["route_destination_required"]


def test_generic_restaurant_trip_keeps_nearby_category_search(provider, monkeypatch):
    def handler(request):
        assert request.url.path.endswith("places:searchNearby")
        assert json.loads(request.content)["includedTypes"] == ["restaurant"]
        return httpx.Response(200, json={"places": []})

    transport(monkeypatch, handler)
    result = asyncio.run(places.answer_nearby(QuestionRequest(
        question="start trip to the nearest restaurant", location={"latitude": 0, "longitude": 0},
    ), "en"))
    assert result[3] == ["places_no_results"]


@pytest.mark.parametrize("language", ["en", "fr", "ar"])
def test_route_passes_language_uses_separate_key_and_coordinate_fallback(provider, monkeypatch, language):
    monkeypatch.setattr(settings, "google_routes_api_key", SecretStr("private-routes"))

    def handler(request):
        body = json.loads(request.content)
        assert body["languageCode"] == language
        assert request.headers["x-goog-api-key"] == "private-routes"
        assert body["destination"] == {"location": {"latLng": {"latitude": 1, "longitude": 2}}}
        return httpx.Response(200, json=route_result())

    transport(monkeypatch, handler)
    origin = QuestionRequest(question="trip", location={"latitude": 0, "longitude": 0}).location
    destination = origin.model_copy(update={"latitude": 1, "longitude": 2})
    route = asyncio.run(directions.walking_route(origin, destination, language))
    assert "500 m" in directions.describe_route(route, "Destination", language)
