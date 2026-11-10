from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services import emergency


def location(**changes):
    return {'latitude': 33.89, 'longitude': 35.5, 'accuracy_meters': 12,
            'captured_at': datetime.now(timezone.utc).isoformat(), **changes}


def mock_brevo(monkeypatch, handler):
    monkeypatch.setattr(settings, 'brevo_api_key', SecretStr('private-brevo-key'))
    monkeypatch.setattr(settings, 'brevo_sender_email', 'sender@example.com')
    original = httpx.AsyncClient
    monkeypatch.setattr(emergency.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_contact_validation_and_removal(client):
    api, _ = client
    assert api.get('/api/v1/emergency/contact').json() == {'email': ''}
    assert api.put('/api/v1/emergency/contact', json={'email': 'not-email'}).status_code == 422
    response = api.put('/api/v1/emergency/contact', json={'email': ' Friend@Example.COM '})
    assert response.json() == {'email': 'friend@example.com'}
    assert api.get('/api/v1/emergency/contact').json() == response.json()
    assert api.put('/api/v1/emergency/contact', json={'email': ''}).status_code == 200
    assert api.post('/api/v1/emergency/location', json=location()).status_code == 409


def test_brevo_uses_saved_recipient_coordinates_maps_and_header_key(client, monkeypatch):
    def handler(request):
        assert str(request.url) == 'https://api.brevo.com/v3/smtp/email'
        assert request.headers['api-key'] == 'private-brevo-key'
        body = json.loads(request.content)
        assert body['to'] == [{'email': 'friend@example.com'}]
        assert body['sender']['email'] == 'sender@example.com'
        assert '33.890000,35.500000' in body['textContent']
        assert 'https://www.google.com/maps/search/?api=1&query=33.890000,35.500000' in body['textContent']
        assert '12 meters' in body['textContent']
        assert '<a href=' in body['htmlContent']
        assert body['headers']['IdempotencyKey'].startswith('sora-sos-')
        return httpx.Response(201, json={'messageId': 'provider-message-id'})
    mock_brevo(monkeypatch, handler)
    api, _ = client
    api.put('/api/v1/emergency/contact', json={'email': 'friend@example.com'})
    result = api.post('/api/v1/emergency/location', json={**location(), 'email': 'attacker@example.com'})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'submitted'


@pytest.mark.parametrize('changes', [
    {'latitude': 91}, {'longitude': -181},
    {'captured_at': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()},
    {'captured_at': datetime.now().isoformat()},
])
def test_invalid_or_stale_location_never_sends(client, monkeypatch, changes):
    mock_brevo(monkeypatch, lambda request: pytest.fail('Invalid location must not be emailed'))
    api, _ = client
    api.put('/api/v1/emergency/contact', json={'email': 'friend@example.com'})
    assert api.post('/api/v1/emergency/location', json=location(**changes)).status_code == 422


def test_missing_config_is_clear_and_provider_errors_are_sanitized(client, monkeypatch):
    api, _ = client
    api.put('/api/v1/emergency/contact', json={'email': 'friend@example.com'})
    assert api.post('/api/v1/emergency/location', json=location()).json()['error']['code'] == 'sos_not_configured'
    mock_brevo(monkeypatch, lambda request: httpx.Response(401, json={'error': 'private-brevo-key'}))
    response = api.post('/api/v1/emergency/location', json=location())
    assert response.status_code == 503
    assert 'private-brevo-key' not in response.text


def test_contacts_are_account_specific_and_send_requires_auth(client):
    api, _ = client
    api.put('/api/v1/emergency/contact', json={'email': 'friend@example.com'})
    other = api.post('/api/v1/auth/register', json={'email': 'other@example.com', 'password': 'a-valid-other-password', 'display_name': 'Other'})
    assert other.status_code == 201
    login = api.post('/api/v1/auth/login', json={'email': 'other@example.com', 'password': 'a-valid-other-password'})
    api.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    assert api.get('/api/v1/emergency/contact').json() == {'email': ''}
    api.headers.pop('Authorization')
    assert api.post('/api/v1/emergency/location', json=location()).status_code == 401


def test_timeout_never_claims_delivery(client, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout('private provider details', request=request)
    mock_brevo(monkeypatch, handler)
    api, _ = client
    api.put('/api/v1/emergency/contact', json={'email': 'friend@example.com'})
    response = api.post('/api/v1/emergency/location', json=location())
    assert response.status_code == 504
    assert response.json()['error']['code'] == 'sos_delivery_unknown'
    assert 'private provider' not in response.text
