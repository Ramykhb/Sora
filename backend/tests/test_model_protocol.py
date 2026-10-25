import asyncio
import httpx
import pytest
from app.core.config import settings
from app.core.errors import BackendError
from app.services.ai.models import Models


class FakeClient:
    response_body = {}
    requests = []

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, json):
        self.requests.append((url, json))
        return httpx.Response(200, json=self.response_body, request=httpx.Request("POST", url))


def test_caption_uses_json_schema_and_actual_image(monkeypatch):
    FakeClient.response_body = {"message": {"content": '{"caption":"A door", "uncertain":false}'}}
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(Models().describe(b"image-bytes"))
    assert result.caption == "A door"
    payload = FakeClient.requests[-1][1]
    assert payload["messages"][1]["images"] == ["aW1hZ2UtYnl0ZXM="]
    assert payload["format"]["properties"]["caption"]


def test_invalid_model_json_is_explicit_failure(monkeypatch):
    FakeClient.response_body = {"message": {"content": "not json"}}
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(BackendError) as error:
        asyncio.run(Models().describe(b"image"))
    assert error.value.code == "vision_unavailable"


def test_embedding_dimension_mismatch_is_rejected(monkeypatch):
    FakeClient.response_body = {"embeddings": [[0.1, 0.2]]}
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(BackendError):
        asyncio.run(Models().embed("door"))


def test_embedding_query_instruction_and_dimension(monkeypatch):
    FakeClient.response_body = {"embeddings": [[0.1] * settings.embedding_dimensions]}
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    vector = asyncio.run(Models().embed("What did the sign say?", query=True))
    assert len(vector) == settings.embedding_dimensions
    assert "Query:" in FakeClient.requests[-1][1]["input"]
