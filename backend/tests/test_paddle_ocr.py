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
    assert engine.recognize(image, "eng") == ("", 0)


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
                                          WORKER.replace("SLEEP", "pass")])
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
