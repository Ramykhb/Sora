import asyncio
import json
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import update

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import Frame
from app.db.models.frame import now
from app.schemas import QuestionRequest
from app.services.ai import depth, gemini, object_finder
from app.services.ai.assistant import answer_question
from app.services.ai.models import models
from app.services.streaming.session import streams
from test_api import create, image_bytes, upload

HTTP_CLIENT = httpx.AsyncClient


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(settings, "gemini_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("private-test-key"))


@pytest.mark.parametrize("question,label", [
    ("Help me find my backpack.", "backpack"), ("Please help me locate the backpack", "backpack"),
    ("Where's my backpack?", "backpack"), ("Where are the backpacks?", "backpack"),
    ("Can you see my phone?", "cell phone"), ("find my backpack right now please", "backpack"),
    ("Aide-moi à trouver mon sac à dos", "backpack"), ("Où est mon sac à dos ?", "backpack"),
    ("ساعدني في العثور على حقيبة ظهري", "backpack"), ("أين حقيبة ظهر؟", "backpack"),
    ("Help me find my red backpack", None), ("Find my keys", None), ("Find my glasses", None),
])
def test_object_request_detection_preserves_attributes_and_supported_aliases(question, label):
    result = object_finder.query(question)
    assert result is not None and result.detector_label == label


@pytest.mark.parametrize("question", [
    "What is in front of me?", "Is it safe to walk?", "route home", "route to there",
    "What is the nearest restaurant?", "Help me find the nearest restaurant",
    "Where was my backpack earlier?", "Find the backpack I saw yesterday",
    "Who is this person?", "Read this sign",
])
def test_other_intents_keep_existing_routes(question):
    assert object_finder.query(question) is None


@pytest.mark.parametrize("horizontal,x", [("left", 15), ("center", 50), ("right", 85)])
@pytest.mark.parametrize("vertical,y", [("top", 15), ("middle", 50), ("bottom", 85)])
def test_detected_box_maps_to_all_nine_image_positions(horizontal, x, vertical, y):
    finding = object_finder.query("help me find my backpack")
    text, uncertain = object_finder.detection_answer(finding, [
        {"label": "backpack", "confidence": .95, "box": [x - 5, y - 5, x + 5, y + 5]},
    ], 100, 100, "en")
    assert not uncertain
    assert "backpack" in text and object_finder.position(horizontal, vertical, "en") in text
    assert "your backpack" not in text
    assert "meters in front of you" in text


@pytest.mark.parametrize("objects", [[],
    [{"label": "chair", "confidence": .99, "box": [0, 0, 100, 100]}],
    [{"label": "backpack", "confidence": .1, "box": [0, 0, 100, 100]}],
    [{"label": "backpack", "confidence": .9, "box": [90, 90, 10, 10]}],
    [{"label": "backpack", "confidence": .9, "box": [0, 0, float("nan"), 100]}],
    [{"label": "backpack", "confidence": .9}],
])
def test_missing_wrong_weak_or_invalid_detections_never_identify_a_target(objects):
    text, uncertain = object_finder.detection_answer(object_finder.query("find my backpack"), objects, 100, 100, "en")
    assert uncertain and "can't identify" in text
    assert "chair" not in text
    assert "not here" not in text


def test_detection_answer_reports_a_coarse_distance_band():
    finding = object_finder.query("find my backpack")
    near_box, far_box = [35, 55, 65, 95], [47, 48, 53, 52]
    near = object_finder.detection_answer(finding, [
        {"label": "backpack", "confidence": .95, "box": near_box},
    ], 100, 100, "en")[0]
    far = object_finder.detection_answer(finding, [
        {"label": "backpack", "confidence": .95, "box": far_box},
    ], 100, 100, "en")[0]
    assert "in front of you" in near and "in front of you" in far
    assert depth.metres("backpack", near_box, 100, 100) < depth.metres("backpack", far_box, 100, 100)


def test_multiple_low_confidence_and_unsupported_attribute_matches_remain_uncertain():
    matches = [{"label": "backpack", "confidence": .9, "box": [0, 60, 20, 90]},
               {"label": "backpack", "confidence": .8, "box": [80, 0, 100, 20]}]
    finding = object_finder.query("find my backpack")
    text, uncertain = object_finder.detection_answer(finding, matches, 100, 100, "en")
    assert uncertain and "Multiple possible matches" in text and "bottom left" in text and "top right" in text
    text, uncertain = object_finder.detection_answer(finding, [{**matches[0], "confidence": .45}], 100, 100, "en")
    assert uncertain and "possible match" in text and "bottom left" in text
    for query in ["find my red backpack", "find my keys"]:
        text, uncertain = object_finder.detection_answer(object_finder.query(query), matches, 100, 100, "en")
        assert uncertain and "confidently" in text
        assert "bottom left" not in text
    assert object_finder.detection_answer(finding, matches[:1], 100, 100, "en", quality_uncertain=True)[1]


@pytest.mark.parametrize("language,position", [("en", "bottom right"), ("fr", "bas à droite"), ("ar", "أسفل اليمين")])
def test_local_finder_retains_fresh_evidence_without_ocr_or_model_queue(client, monkeypatch, language, position):
    import app.services.frames.ingestion as ingestion

    api, _ = client
    sid = UUID(create(api))

    def forbidden(*args, **kwargs):
        raise AssertionError("Object finding must not queue behind OCR, local VLM, or embeddings")

    for name in ["read_text", "analyze_image"]:
        monkeypatch.setattr(ingestion, name, forbidden)
    for name in ["chat", "embed", "describe"]:
        monkeypatch.setattr(models, name, forbidden)

    async def exercise():
        state = streams.start(sid, "test")
        state.observation_content = image_bytes()
        state.observation = {"captured_at": now().isoformat(), "expires_at": (now() + timedelta(seconds=2)).isoformat(),
                             "width": 100, "height": 100, "detected_objects": [
                                 {"label": "backpack", "confidence": .95, "box": [70, 70, 95, 95]},
                                 {"label": "tv", "confidence": .99, "box": [0, 0, 30, 30]},
                             ]}
        try:
            async with ingestion.session_lock(sid), models.gate.slot(), asyncio.timeout(2):
                return await answer_question(sid, QuestionRequest(question="help me find my backpack", language=language))
        finally:
            await streams.stop(sid)

    result = api.portal.call(exercise)
    assert position in result.answer and not result.uncertain
    assert result.evidence_frame_ids and "tv" not in result.answer


def test_finder_does_not_retime_stale_memory_into_current_object_location(client):
    api, factory = client
    sid = create(api)
    frame = upload(api, sid)

    async def age():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frame["id"])).values(captured_at=now() - timedelta(seconds=5)))
            await db.commit()

    api.portal.call(age)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "find my backpack", "scope": "memory"}).json()
    assert result["uncertain"] and not result["evidence_frame_ids"]
    assert "recent camera view" in result["answer"]


@pytest.mark.parametrize("status,horizontal,vertical,uncertain,prefix", [
    ("visible", "left", "bottom", False, "A matching object is visible near the bottom left"),
    ("not_visible", "unknown", "unknown", False, "I can't identify the requested object"),
    ("uncertain", "right", "middle", True, "I can't locate the requested object confidently"),
    ("visible", "unknown", "middle", False, "I can't locate the requested object confidently"),
])
def test_cloud_finder_distinguishes_visible_absent_and_ambiguous_matches(client, cloud, monkeypatch, status, horizontal, vertical, uncertain, prefix):
    api, _ = client
    sid = create(api)
    upload(api, sid)

    async def assess(image, question, language):
        assert image and question == "help me find my backpack"
        return gemini.GeminiAnswer(answer="The bag shape is visible beside a table.", uncertain=uncertain,
                                   object_status=status, object_horizontal=horizontal, object_vertical=vertical)

    monkeypatch.setattr(gemini, "ask_image", assess)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "help me find my backpack"}).json()
    assert result["answer"].startswith(prefix)
    assert result["uncertain"] == (uncertain or status != "visible" or horizontal == "unknown")
    assert result["evidence_frame_ids"]


@pytest.mark.parametrize("fields", [
    {"object_status": "visible", "object_horizontal": "left", "object_vertical": "bottom"},
    {"object_status": "not_visible", "object_horizontal": "unknown", "object_vertical": "unknown"},
    {"object_status": "visible", "object_horizontal": "north", "object_vertical": "bottom"},
    {},
])
def test_gemini_object_protocol_requires_bounded_status_and_image_relative_positions(cloud, monkeypatch, fields):
    def handle(request):
        payload = json.loads(request.content)
        schema = payload["generationConfig"]["responseJsonSchema"]
        assert {"object_status", "object_horizontal", "object_vertical", "object_distance"} <= set(schema["required"])
        assert "unknown" in schema["properties"]["object_distance"]["enum"]
        assert "visible_path" not in schema["required"]
        instructions = payload["systemInstruction"]["parts"][0]["text"]
        assert "object-finding request" in instructions and "not proof of ownership" in instructions
        assert "Do not substitute a similar object" in instructions
        assert "never state a precise distance" in instructions
        response = {"answer": "A dark backpack is beside a table.", "uncertain": False,
                    "object_distance": "about_2m", **fields}
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(response)}]}}]})

    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(handle), **kw))
    if not fields or fields.get("object_horizontal") == "north":
        with pytest.raises(BackendError) as error:
            asyncio.run(gemini.ask_image(b"sanitized-jpeg", "find my backpack", "en"))
        assert error.value.code == "gemini_unavailable"
    else:
        assert asyncio.run(gemini.ask_image(b"sanitized-jpeg", "find my backpack", "en")).object_status == fields["object_status"]


def test_failed_cloud_finding_uses_target_specific_detection_instead_of_generic_overview(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)  # The fixture detects a chair, never a backpack.

    async def fail(*args):
        raise BackendError("Provider unavailable", 503, "gemini_unavailable")

    monkeypatch.setattr(gemini, "ask_image", fail)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "help me find my backpack"}).json()
    assert result["uncertain"] and "can't identify the requested object" in result["answer"]
    assert "chair" not in result["answer"]
    assert "local_detection_fallback" in result["processing_warnings"]


def test_no_camera_view_never_requests_provider_or_claims_an_object_location(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)

    async def forbidden(*args):
        raise AssertionError("No object inference without camera evidence")

    monkeypatch.setattr(gemini, "ask_image", forbidden)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "find my backpack"}).json()
    assert result["uncertain"] and not result["evidence_frame_ids"]
    assert "recent camera view" in result["answer"]


def test_poor_quality_camera_evidence_downgrades_a_confident_cloud_match(client, cloud, monkeypatch):
    api, factory = client
    sid = create(api)
    frame = upload(api, sid)

    async def mark_quality():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frame["id"])).values(processing_warnings=["quality_override"]))
            await db.commit()

    api.portal.call(mark_quality)

    async def assess(*args):
        return gemini.GeminiAnswer(answer="A bag shape is partially visible.", uncertain=False,
                                   object_status="visible", object_horizontal="left", object_vertical="bottom")

    monkeypatch.setattr(gemini, "ask_image", assess)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "find my backpack"}).json()
    assert result["uncertain"] and result["answer"].startswith("I can't locate the requested object confidently")


def test_safety_equipment_finding_is_not_misrouted_to_walking_assessment(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)

    def handle(request):
        payload = json.loads(request.content)
        required = payload["generationConfig"]["responseJsonSchema"]["required"]
        assert "object_status" in required and "visible_path" not in required
        result = {"answer": "A yellow helmet is beside the table.", "uncertain": False,
                  "object_status": "visible", "object_horizontal": "right", "object_vertical": "middle",
                  "object_distance": "about_2m"}
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}]})

    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(handle), **kw))
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Help me find my safety helmet"}).json()
    assert not result["uncertain"] and "on the right" in result["answer"]
    assert "visible path" not in result["answer"]


@pytest.mark.parametrize("elapsed", [3, 7])
def test_cloud_object_locations_allow_bounded_inference_time_but_reject_old_results(client, cloud, monkeypatch, elapsed):
    from app.services.ai import assistant, cloud_view

    api, _ = client
    sid = create(api)
    upload(api, sid)
    offset = [0]

    def clock():
        return now() + timedelta(seconds=offset[0])

    monkeypatch.setattr(cloud_view, "now", clock)
    monkeypatch.setattr(assistant, "now", clock)
    monkeypatch.setattr(settings, "object_finder_max_age_seconds", 6)

    async def assess(*args):
        offset[0] = elapsed
        return gemini.GeminiAnswer(answer="A black backpack rests beside the table.", uncertain=False,
                                   object_status="visible", object_horizontal="left", object_vertical="bottom")

    monkeypatch.setattr(gemini, "ask_image", assess)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "find my backpack"}).json()
    if elapsed == 3:
        assert not result["uncertain"] and "bottom left" in result["answer"]
        assert result["evidence_frame_ids"]
    else:
        assert result["uncertain"] and "black backpack" not in result["answer"]
        assert "gemini_evidence_stale" in result["processing_warnings"]
