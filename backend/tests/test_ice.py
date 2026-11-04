from pydantic import SecretStr

from app.core.config import settings
from app.services.streaming.ice import ice_servers


def test_public_turn_tunnel_keeps_internal_relay_local(monkeypatch):
    monkeypatch.setattr(settings, "ice_servers", [])
    monkeypatch.setattr(settings, "turn_public_host", "192.168.1.10")
    monkeypatch.setattr(settings, "turn_internal_host", "turn")
    monkeypatch.setattr(settings, "turn_shared_secret", SecretStr("test-secret"))
    public_urls = ["turn:example.com:20482?transport=tcp"]
    monkeypatch.setattr(settings, "turn_public_urls", public_urls)

    public = ice_servers()[-1]
    internal = ice_servers(internal=True)[-1]
    assert public["urls"] == public_urls
    assert internal["urls"] == ["turn:turn:3478?transport=udp", "turn:turn:3478?transport=tcp"]
    assert public["credential"] != "test-secret"

    monkeypatch.setattr(settings, "turn_public_urls", [])
    assert ice_servers()[-1]["urls"] == [
        "turn:192.168.1.10:3478?transport=udp", "turn:192.168.1.10:3478?transport=tcp",
    ]
