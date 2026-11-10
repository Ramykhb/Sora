import subprocess
import sys
from time import monotonic

import numpy as np
import pytest

from app.core.config import settings
from app.core.errors import BackendError
from app.services.frames import ocr, paddle_client
from app.services.frames.paddle_worker import PaddleEngine, combine_regions, recognition_languages


def box(x, y=10):
    return np.float32([[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]])


def test_missing_models_fail_before_importing_runtime_or_downloading(tmp_path):
    with pytest.raises(FileNotFoundError, match="Prepare local PaddleOCR"):
        PaddleEngine(tmp_path, 2, 0.6, 64)


def test_script_selection_and_reading_order():
    assert recognition_languages("eng+fra+ara") == ["latin", "arabic"]
    assert recognition_languages("eng") == ["english"]
    assert recognition_languages("ara") == ["arabic"]
    with pytest.raises(ValueError):
        recognition_languages("unknown")
    text, confidence = combine_regions([(box(90), "123", 0.9), (box(10), "EXIT", 0.95)])
    assert text == "EXIT 123" and 90 <= confidence <= 95
    assert combine_regions([(box(10), "123", 0.9), (box(90), "مخرج", 0.95)])[0] == "مخرج 123"


def test_paddle_discards_background_and_low_confidence_without_mutating_pixels():
    class Detector:
        polygons = [box(10), box(90)]
        def predict(self, image):
            return iter([{"dt_polys": self.polygons}])
    class Recognizer:
        def predict(self, images, batch_size):
            assert len(images) == 2
            return iter([{"rec_text": "EXIT", "rec_score": 0.99},
                         {"rec_text": "garbage", "rec_score": 0.2}])
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.detector, engine.recognizers = Detector(), {"english": Recognizer()}
    engine.minimum_confidence, engine.max_regions = 0.6, 64
    image = np.full((100, 200, 3), 240, np.uint8)
    saved = image.copy()
    assert engine.recognize(image, "eng")[0] == "EXIT"
    assert np.array_equal(image, saved)
    engine.detector.polygons = []
    assert engine.recognize(image, "eng") == ("", 0, False)


def test_configured_engine_routes_to_paddle(monkeypatch):
    image = np.zeros((32, 32, 3), np.uint8)
    monkeypatch.setattr(settings, "ocr_engine", "paddleocr")
    def recognize(received, languages):
        assert received is image and languages == "fra"
        return "Entrée", 99
    monkeypatch.setattr(paddle_client.paddle_ocr, "recognize", recognize)
    assert ocr.recognize_text(image, "fra") == ("Entrée", 99)


WORKER = """
import base64, json, sys, time
print('native library startup message', flush=True)
print(json.dumps({'type': 'ready'}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    assert base64.b64decode(request['image']).startswith(b'\\x89PNG')
    SLEEP
    print(json.dumps({'id': request['id'], 'text': 'EXIT 123', 'confidence': 99}), flush=True)
"""


def fake_workers(monkeypatch, scripts):
    real_popen = subprocess.Popen
    processes = []
    def popen(*args, **kwargs):
        script = scripts[min(len(processes), len(scripts) - 1)]
        process = real_popen([sys.executable, "-u", "-c", script], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(paddle_client.subprocess, "Popen", popen)
    return processes


def test_worker_is_reused_and_closed_without_reloading_models(monkeypatch):
    processes = fake_workers(monkeypatch, [WORKER.replace("SLEEP", "pass")])
    client = paddle_client.PaddleOCRClient()
    try:
        client.warmup()
        for _ in range(2):
            assert client.recognize(np.zeros((32, 32, 3), np.uint8), "eng") == ("EXIT 123", 99)
        assert client.ready and len(processes) == 1
    finally:
        client.close()
    assert processes[0].poll() is not None and not client.ready


def test_timeout_stops_stuck_inference_and_next_request_recovers(monkeypatch):
    processes = fake_workers(monkeypatch, [WORKER.replace("SLEEP", "time.sleep(10)"),
                                          "import time; time.sleep(0.35)\n" + WORKER.replace("SLEEP", "pass")])
    monkeypatch.setattr(settings, "ocr_timeout_seconds", 0.2)
    client = paddle_client.PaddleOCRClient()
    try:
        client.warmup()
        started = monotonic()
        with pytest.raises(BackendError) as error:
            client.recognize(np.zeros((32, 32, 3), np.uint8), "eng")
        assert error.value.code == "ocr_timeout" and monotonic() - started < 1
        assert processes[0].poll() is not None
        assert client.recognize(np.zeros((32, 32, 3), np.uint8), "eng") == ("EXIT 123", 99)
        assert len(processes) == 2
    finally:
        client.close()


def test_cold_model_startup_is_separate_from_frame_deadline(monkeypatch):
    processes = fake_workers(monkeypatch, ["import time; time.sleep(0.35)\n" + WORKER.replace("SLEEP", "pass")])
    monkeypatch.setattr(settings, "ocr_timeout_seconds", 0.2)
    client = paddle_client.PaddleOCRClient()
    try:
        assert client.recognize(np.zeros((32, 32, 3), np.uint8), "eng") == ("EXIT 123", 99)
        assert client.recognize(np.zeros((32, 32, 3), np.uint8), "eng") == ("EXIT 123", 99)
        assert len(processes) == 1
    finally:
        client.close()


def test_budget_exhaustion_without_text_does_not_discard_warm_models(monkeypatch):
    script = WORKER.replace("SLEEP", "pass").replace(
        "'text': 'EXIT 123',", "'text': '' if request['languages'] == 'ara' else 'EXIT 123', 'partial': request['languages'] == 'ara',")
    processes = fake_workers(monkeypatch, [script])
    client = paddle_client.PaddleOCRClient()
    try:
        client.warmup()
        with pytest.raises(BackendError) as error:
            client.recognize(np.zeros((32, 32, 3), np.uint8), "ara")
        assert error.value.code == "ocr_timeout" and client.ready
        assert client.recognize(np.zeros((32, 32, 3), np.uint8), "eng") == ("EXIT 123", 99)
        assert len(processes) == 1
    finally:
        client.close()


def test_warmup_runs_detector_and_all_recognizers():
    shapes = []
    class Predictor:
        def predict(self, image):
            shapes.append(image.shape)
            return iter([{}])
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.detector = Predictor()
    engine.recognizers = {language: Predictor() for language in ["english", "latin", "arabic"]}
    engine.warmup()
    assert shapes == [(1280, 720, 3), *[(48, 320, 3)] * 3]


def test_time_budget_preserves_completed_regions_and_marks_partial(monkeypatch):
    from app.services.frames import paddle_worker
    clock = [0.0]
    monkeypatch.setattr(paddle_worker, "monotonic", lambda: clock[0])
    class Detector:
        def predict(self, image):
            return iter([{"dt_polys": [box(10), box(90), box(160)]}])
    class Recognizer:
        def predict(self, images, batch_size):
            assert len(images) <= 2 and batch_size == 2
            clock[0] += 0.4
            return iter({"rec_text": text, "rec_score": 0.99} for text in ["EXIT", "123"][:len(images)])
    engine = PaddleEngine.__new__(PaddleEngine)
    engine.detector, engine.recognizers = Detector(), {"english": Recognizer()}
    engine.minimum_confidence, engine.max_regions = 0.6, 64
    text, confidence, partial = engine.recognize(np.zeros((100, 250, 3), np.uint8), "eng", 0.6)
    assert text == "EXIT 123" and confidence > 98 and partial
    assert clock[0] < 0.6


def test_partial_result_metadata_survives_existing_tuple_interface(monkeypatch):
    from app.services.frames.ocr_result import OCRResult
    result = OCRResult("EXIT", 99, ["ocr_partial"])
    assert tuple(result) == ("EXIT", 99)
    assert result.warnings == ("ocr_partial",)


def test_partial_ocr_is_preserved_in_stored_live_frame(client, monkeypatch):
    from functools import partial
    from uuid import UUID
    from app.services.frames import ingestion
    from app.services.frames.ocr_result import OCRResult
    from test_api import create, image_bytes
    api, _ = client
    sid = create(api)
    monkeypatch.setattr(ingestion, "read_text", lambda *args: OCRResult("EXIT", 99, ["ocr_partial"]))
    result = api.portal.call(partial(ingestion.ingest_bytes, image_bytes(), UUID(sid),
                                    force=True, defer_enrichment=True, detected_objects=[]))
    frame = api.get(f"/api/v1/sessions/{sid}/frames/{result.frame.id}").json()
    assert frame["ocr_text"] == "EXIT" and "ocr_partial" in frame["processing_warnings"]
