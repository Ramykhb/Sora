import base64
import hashlib
import hmac
import time
from app.core.config import settings


def ice_servers(*, internal=False):
    servers = list(settings.ice_servers)
    secret = settings.turn_shared_secret.get_secret_value()
    if settings.turn_public_host and secret:
        host = settings.turn_internal_host if internal else settings.turn_public_host
        username = str(int(time.time()) + 3600)
        credential = base64.b64encode(
            hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
        ).decode()
        servers.append({
            "urls": [f"turn:{host}:3478?transport=udp", f"turn:{host}:3478?transport=tcp"],
            "username": username, "credential": credential,
        })
    return servers


def rtc_configuration():
    from aiortc import RTCConfiguration, RTCIceServer

    return RTCConfiguration(iceServers=[RTCIceServer(**item) for item in ice_servers(internal=True)])
