"""Persistent, deadline-bounded access to the isolated local PaddleOCR runtime."""
import base64
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
from time import monotonic
from uuid import uuid4

import cv2

from app.core.config import BACKEND_ROOT, settings
from app.core.errors import BackendError
from app.services.frames.ocr_result import OCRResult


class PaddleOCRClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.buffer = b""
        self.initialized = False

    @property
    def ready(self):
        process = self.process
        return bool(self.initialized and process and process.poll() is None)

    def _message(self, deadline):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while True:
                while b"\n" in self.buffer:
                    line, self.buffer = self.buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue  # Some native libraries write startup diagnostics to stdout.
                    if isinstance(message, dict):
                        return message
                remaining = deadline - monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("PaddleOCR deadline exceeded")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("PaddleOCR worker exited")
                self.buffer += chunk
                if len(self.buffer) > 2 * 1024 * 1024:
                    raise RuntimeError("Invalid PaddleOCR worker response")

    def _start(self, deadline):
        if self.ready:
            return
        if self.process is None or self.process.poll() is not None:
            self._stop()
            local_python = settings.paddle_ocr_model_dir / ".venv" / "bin" / "python"
            executable = settings.paddle_ocr_python or (
                str(local_python) if local_python.is_file() else sys.executable)
            environment = {**os.environ, "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
                           "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
            self.process = subprocess.Popen(
                [executable, "-u", str(Path(__file__).with_name("paddle_worker.py")),
                 "--model-directory", str(settings.paddle_ocr_model_dir),
                 "--threads", str(settings.ocr_threads),
                 "--min-confidence", str(settings.ocr_min_word_confidence / 100),
                 "--max-regions", str(settings.ocr_max_regions)],
                cwd=BACKEND_ROOT, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            )
            os.set_blocking(self.process.stdin.fileno(), False)
        message = self._message(deadline)
        if message.get("type") != "ready":
            raise RuntimeError("PaddleOCR worker initialization failed")
        self.initialized = True

    def _send(self, message, deadline):
        content = memoryview((json.dumps(message) + "\n").encode())
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while content:
                remaining = deadline - monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("PaddleOCR send deadline exceeded")
                try:
                    sent = os.write(self.process.stdin.fileno(), content)
                    content = content[sent:]
                except BlockingIOError:
                    continue

    def warmup(self):
        with self.lock:
            try:
                self._start(monotonic() + 45)
            except Exception as exc:
                self._stop()
                raise BackendError("PaddleOCR unavailable; prepare its runtime and model files", 503,
                                   "ocr_unavailable") from exc

    def recognize(self, image, languages):
        queued_at = monotonic()
        if not self.lock.acquire(timeout=settings.ocr_timeout_seconds):
            raise BackendError("OCR is busy; try again", 503, "ocr_busy")
        try:
            queue_seconds = monotonic() - queued_at
            # A replacement worker needs the same startup allowance as initial
            # API warmup. Charging model reload to a 4s inference deadline kills
            # every replacement before it can answer, creating a timeout loop.
            self._start(monotonic() + 45)
            deadline = monotonic() + max(0, settings.ocr_timeout_seconds - queue_seconds)
            ok, encoded = cv2.imencode(".png", image)
            if not ok:
                raise ValueError("Cannot encode OCR image")
            request_id = uuid4().hex
            message = {"id": request_id, "languages": languages,
                       "timeout_seconds": max(0.01, deadline - monotonic() - 0.3),
                       "image": base64.b64encode(encoded).decode("ascii")}
            # Only sanitized pixels from prepare_image reach this local worker.
            self._send(message, deadline)
            response = self._message(deadline)
            if response.get("id") != request_id:
                raise RuntimeError("Invalid PaddleOCR response")
            if "error" in response:
                raise BackendError("PaddleOCR failed to recognize the image", 503, "ocr_unavailable")
            if response.get("partial") and not response["text"]:
                raise BackendError("OCR reached its time limit before text could be read", 503, "ocr_timeout")
            return OCRResult(response["text"], float(response["confidence"]),
                             ["ocr_partial"] if response.get("partial") else [])
        except BackendError:
            raise
        except TimeoutError as exc:
            self._stop()
            raise BackendError("OCR timed out; try a smaller or clearer text region", 503,
                               "ocr_timeout") from exc
        except Exception as exc:
            self._stop()
            raise BackendError("PaddleOCR unavailable; check its runtime and models", 503,
                               "ocr_unavailable") from exc
        finally:
            self.lock.release()

    def _stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
        self.process, self.buffer, self.initialized = None, b"", False

    def close(self):
        with self.lock:
            self._stop()


paddle_ocr = PaddleOCRClient()
