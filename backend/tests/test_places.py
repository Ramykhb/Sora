import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import settings
from app.schemas import QuestionRequest
from app.services.ai import places
from test_api import create


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(settings, 'google_place_api_key', SecretStr('private-google'))
    monkeypatch.setattr(settings, 'groq_api_key', SecretStr('private-groq'))


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(places.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_protocol_and_distance(client, provider, monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        if request.url.host == 'api.groq.com':
            assert body['model'] == 'openai/gpt-oss-20b'
            assert body['response_format']['json_schema']['strict'] is True
            assert request.headers['authorization'] == 'Bearer private-groq'
            content = json.dumps({'query': "McDonald's", 'restaurant_only': False})
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]})
        assert request.url.path.endswith('places:searchText')
        assert body['textQuery'] == "McDonald's"
        assert body['rankPreference'] == 'DISTANCE'
        assert body['locationBias']['circle']['center']['latitude'] == 0
        assert request.headers['x-goog-api-key'] == 'private-google'
        return httpx.Response(200, json={'places': [
            {'displayName': {'text': 'Far branch'}, 'location': {'latitude': 0.01, 'longitude': 0}},
            {'displayName': {'text': "McDonald's"}, 'location': {'latitude': 0.0036, 'longitude': 0}},
        ]})
    transport(monkeypatch, handler)
    api, _ = client
    sid = create(api)
    response = api.post(f'/api/v1/sessions/{sid}/questions', json={
        'question': 'what is the closes mcdonalds', 'location': {'latitude': 0, 'longitude': 0},
    })
    assert response.status_code == 200
    answer = response.json()
    assert "McDonald's" in answer['answer'] and '400 m' in answer['answer']
    assert answer['answer'] == "The closest McDonald's is approximately 400 m away."
    assert answer['evidence_frame_ids'] == []
    assert not answer['uncertain']


def test_generic_fallback(provider, monkeypatch):
    def handler(request):
        if request.url.host == 'api.groq.com':
            return httpx.Response(429, json={'error': 'private-groq'})
        assert request.url.path.endswith('places:searchNearby')
        assert json.loads(request.content)['includedTypes'] == ['restaurant']
        return httpx.Response(200, json={'places': []})
    transport(monkeypatch, handler)
    result = asyncio.run(places.answer_nearby(QuestionRequest(
        question='what is the closest resteraunt', location={'latitude': 33, 'longitude': 35},
    ), 'en'))
    assert result[1] is True
    assert result[3] == ['groq_unavailable', 'places_no_results']


def test_missing_gps(provider, monkeypatch):
    transport(monkeypatch, lambda request: pytest.fail('No provider without GPS'))
    answer = asyncio.run(places.answer_nearby(QuestionRequest(question='closest restaurant'), 'en'))
    assert answer[3] == ['location_required']


@pytest.mark.parametrize('status,payload', [(403, {'error': 'private-google'}), (200, {'places': [{}]})])
def test_sanitized_errors(provider, monkeypatch, status, payload):
    monkeypatch.setattr(settings, 'groq_api_key', SecretStr(''))
    transport(monkeypatch, lambda request: httpx.Response(status, json=payload))
    answer = asyncio.run(places.answer_nearby(QuestionRequest(
        question='closest restaurant', location={'latitude': 0, 'longitude': 0},
    ), 'en'))
    assert answer[3] == ['places_unavailable']
    assert 'private-google' not in answer[0]


@pytest.mark.parametrize('latitude,longitude', [(91, 0), (0, -181), (float('nan'), 0)])
def test_invalid_gps(latitude, longitude):
    with pytest.raises(ValidationError):
        QuestionRequest(question='nearest restaurant', location={'latitude': latitude, 'longitude': longitude})


@pytest.mark.parametrize('question', ['How far is the chair?', 'What is the closest object in the camera?', 'Read the nearby sign'])
def test_visual_questions_keep_camera_path(question):
    assert not places.is_place_question(question)


def test_outside_radius_and_closed_places_are_not_reported(provider, monkeypatch):
    monkeypatch.setattr(settings, 'groq_api_key', SecretStr(''))
    transport(monkeypatch, lambda request: httpx.Response(200, json={'places': [
        {'displayName': {'text': 'Remote'}, 'location': {'latitude': 1, 'longitude': 0}},
        {'displayName': {'text': 'Closed'}, 'location': {'latitude': 0, 'longitude': 0}, 'businessStatus': 'CLOSED_PERMANENTLY'},
    ]}))
    answer = asyncio.run(places.answer_nearby(QuestionRequest(
        question='closest restaurant', location={'latitude': 0, 'longitude': 0},
    ), 'en'))
    assert answer[3] == ['places_no_results']


@pytest.mark.parametrize('name,expected', [
    ('Mc Donna Burger - Restaurant', False),
    ("McDonald's Ain El Mreisseh", True),
    ('McDonald’s Beirut', True),
    ("Mc Donald's", True),
    ('ماكدونالدز الحمرا', True),
    ('McDonaldsville Burgers', False),
])
def test_brand_name_matching(name, expected):
    assert places.matches_named_place(name, "McDonald's") is expected


@pytest.mark.parametrize('groq_available', [True, False])
def test_unrelated_restaurant_is_never_substituted_for_mcdonalds(provider, monkeypatch, groq_available):
    if not groq_available:
        monkeypatch.setattr(settings, 'groq_api_key', SecretStr(''))
    def handler(request):
        if request.url.host == 'api.groq.com':
            # Even incorrect category extraction must preserve the explicit brand.
            content = json.dumps({'query': 'burger restaurant', 'restaurant_only': True, 'named_place': None})
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]})
        assert json.loads(request.content)['textQuery'] == "McDonald's"
        return httpx.Response(200, json={'places': [
            {'displayName': {'text': 'Mc Donna Burger - Restaurant'}, 'location': {'latitude': 0.0036, 'longitude': 0}},
            {'displayName': {'text': "McDonald's Branch"}, 'location': {'latitude': 0.0243, 'longitude': 0}},
        ]})
    transport(monkeypatch, handler)
    answer = asyncio.run(places.answer_nearby(QuestionRequest(
        question='what is the closest mcdonalds', location={'latitude': 0, 'longitude': 0},
    ), 'en'))
    assert answer[0] == "The closest McDonald's is approximately 2.7 km away."
    assert answer[1] is False


def test_only_unrelated_matches_returns_no_results(provider, monkeypatch):
    monkeypatch.setattr(settings, 'groq_api_key', SecretStr(''))
    transport(monkeypatch, lambda request: httpx.Response(200, json={'places': [
        {'displayName': {'text': 'Mc Donna Burger - Restaurant'}, 'location': {'latitude': 0.0243, 'longitude': 0}},
    ]}))
    answer = asyncio.run(places.answer_nearby(QuestionRequest(
        question='closest mcdonalds', location={'latitude': 0, 'longitude': 0},
    ), 'en'))
    assert answer[0] == "I couldn't find a matching McDonald's within 5 km."
    assert answer[1] is True
    assert answer[3] == ['places_no_results']


def test_other_named_chain_is_also_filtered(provider, monkeypatch):
    def handler(request):
        if request.url.host == 'api.groq.com':
            content = json.dumps({'query': 'Starbucks', 'restaurant_only': False, 'named_place': 'Starbucks'})
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]})
        return httpx.Response(200, json={'places': [
            {'displayName': {'text': 'Star Burger Coffee'}, 'location': {'latitude': 0.001, 'longitude': 0}},
            {'displayName': {'text': 'Starbucks Hamra'}, 'location': {'latitude': 0.0036, 'longitude': 0}},
        ]})
    transport(monkeypatch, handler)
    answer = asyncio.run(places.answer_nearby(QuestionRequest(
        question='closest starbucks', location={'latitude': 0, 'longitude': 0},
    ), 'en'))
    assert answer[0] == 'The closest Starbucks is approximately 400 m away.'
