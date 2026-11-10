"""Local-only OCR worker; stdin/stdout JSON-lines, no HTTP listener or downloads."""
import argparse
import base64
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from time import monotonic
import unicodedata

import cv2
import numpy as np

MODELS = {"english": "en_PP-OCRv5_mobile_rec", "latin": "latin_PP-OCRv5_mobile_rec",
          "arabic": "arabic_PP-OCRv5_mobile_rec"}


def recognition_languages(languages):
    requested = set(languages.lower().replace(",", "+").split("+"))
    selected = []
    if requested & {"fr", "fra", "french"}:
        selected.append("latin")  # Also recognizes English and accented Latin text.
    elif requested & {"en", "eng", "english"}:
        selected.append("english")
    if requested & {"ar", "ara", "arabic"}:
        selected.append("arabic")
    if not selected:
        raise ValueError("Unsupported OCR language")
    return selected


def crop_text(image, polygon):
    points = np.asarray(polygon, np.float32)
    width = max(2, round(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3]))))
    height = max(2, round(max(np.linalg.norm(points[0] - points[3]), np.linalg.norm(points[1] - points[2]))))
    target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    result = cv2.warpPerspective(image, cv2.getPerspectiveTransform(points, target), (width, height),
                                 flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return np.rot90(result) if height > width * 1.5 else result


def combine_regions(regions):
    lines = []
    for polygon, text, confidence in sorted(regions, key=lambda item: float(np.mean(item[0][:, 1]))):
        center = float(np.mean(polygon[:, 1]))
        height = max(2, float(np.max(polygon[:, 1]) - np.min(polygon[:, 1])))
        line = next((line for line in lines if abs(line[0] - center) < max(line[1], height) * 0.5), None)
        if line is None:
            line = [center, height, []]
            lines.append(line)
        line[2].append((float(np.mean(polygon[:, 0])), text, confidence))
    output, scores = [], []
    for _, _, words in lines:
        rtl = any("\u0600" <= char <= "\u06ff" for _, text, _ in words for char in text)
        words.sort(key=lambda word: word[0], reverse=rtl)
        output.append(" ".join(text for _, text, _ in words))
        scores.extend((confidence, sum(char.isalnum() for char in text)) for _, text, confidence in words)
    weight = sum(length for _, length in scores)
    confidence = sum(score * length for score, length in scores) / max(1, weight)
    return "\n".join(output), confidence * 100


class PaddleEngine:
    def __init__(self, directory, threads, minimum_confidence, max_regions):
        for name in ["PP-OCRv5_mobile_det", *MODELS.values()]:
            for filename in ("inference.json", "inference.pdiparams", "inference.yml"):
                if not (directory / f"{name}_infer" / filename).is_file():
                    raise FileNotFoundError(f"Prepare local PaddleOCR model first: {name}")
        from paddleocr import TextDetection, TextRecognition

        cv2.setNumThreads(threads)
        options = {"device": "cpu", "cpu_threads": threads, "enable_mkldnn": False}
        self.detector = TextDetection(
            model_name="PP-OCRv5_mobile_det", model_dir=str(directory / "PP-OCRv5_mobile_det_infer"),
            limit_side_len=1280, limit_type="max", **options)
        self.recognizers = {
            language: TextRecognition(model_name=name, model_dir=str(directory / f"{name}_infer"), **options)
            for language, name in MODELS.items()
        }
        self.minimum_confidence, self.max_regions = minimum_confidence, max_regions

    def warmup(self):
        # Initialize native inference paths at camera resolution before READY,
        # instead of charging first-inference setup to the first saved frame.
        camera = np.full((1280, 720, 3), 255, np.uint8)
        next(iter(self.detector.predict(camera)))
        line = np.full((48, 320, 3), 255, np.uint8)
        cv2.putText(line, "WARMUP 123", (5, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        for recognizer in self.recognizers.values():
            next(iter(recognizer.predict(line)))

    def recognize(self, image, languages, budget_seconds=None):
        deadline = monotonic() + budget_seconds if budget_seconds is not None else float("inf")
        selected = recognition_languages(languages)
        detection = next(iter(self.detector.predict(image)))
        detected = list(detection["dt_polys"])
        # Read the most legible regions before tiny glyphs/icons consume the
        # frame budget. Reconstruct spatial reading order after recognition.
        polygons = sorted(detected, key=lambda polygon: cv2.contourArea(np.float32(polygon)),
                          reverse=True)[:self.max_regions]
        partial = len(detected) > len(polygons)
        if not polygons:
            return "", 0.0, False
        crops = [crop_text(image, polygon) for polygon in polygons]
        best = [None] * len(crops)
        estimated_batch_seconds = 0.1
        for offset in range(0, len(crops), 2):
            for language in selected:
                if deadline - monotonic() < estimated_batch_seconds:
                    text, confidence = combine_regions([region for region in best if region is not None])
                    return text, confidence, True
                started = monotonic()
                for index, result in enumerate(self.recognizers[language].predict(crops[offset:offset + 2], batch_size=2), offset):
                    text = "".join(char for char in result["rec_text"].strip()
                                   if unicodedata.category(char) != "Cf")
                    score = float(result["rec_score"])
                    if sum(char.isalnum() for char in text) < 2 or score < self.minimum_confidence:
                        continue
                    if best[index] is None or score > best[index][2]:
                        best[index] = (np.asarray(polygons[index]), text, score)
                estimated_batch_seconds = max(estimated_batch_seconds, (monotonic() - started) * 1.5)
        text, confidence = combine_regions([region for region in best if region is not None])
        return text, confidence, partial


def serve(engine):
    print(json.dumps({"type": "ready", "engine": "paddleocr"}), flush=True)
    for line in sys.stdin.buffer:
        message = {}
        try:
            message = json.loads(line)
            raw = base64.b64decode(message["image"], validate=True)
            image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Invalid OCR image")
            with redirect_stdout(sys.stderr):
                text, confidence, partial = engine.recognize(image, message["languages"], message.get("timeout_seconds"))
            response = {"id": message["id"], "text": text, "confidence": confidence, "partial": partial}
        except Exception:
            response = {"id": message.get("id"), "error": "ocr_failed"}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--max-regions", type=int, default=64)
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        engine = PaddleEngine(args.model_directory, args.threads, args.min_confidence, args.max_regions)
        engine.warmup()
    serve(engine)
