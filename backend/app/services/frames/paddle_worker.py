"""Local-only OCR worker; stdin/stdout JSON-lines, no HTTP listener or downloads."""
import argparse
import base64
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
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

    def recognize(self, image, languages):
        selected = recognition_languages(languages)
        detection = next(iter(self.detector.predict(image)))
        polygons = list(detection["dt_polys"])[:self.max_regions]
        if not polygons:
            return "", 0.0
        crops = [crop_text(image, polygon) for polygon in polygons]
        best = [None] * len(crops)
        for language in selected:
            for index, result in enumerate(self.recognizers[language].predict(crops, batch_size=8)):
                text = "".join(char for char in result["rec_text"].strip()
                               if unicodedata.category(char) != "Cf")
                score = float(result["rec_score"])
                if sum(char.isalnum() for char in text) < 2 or score < self.minimum_confidence:
                    continue
                if best[index] is None or score > best[index][2]:
                    best[index] = (np.asarray(polygons[index]), text, score)
        return combine_regions([region for region in best if region is not None])


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
                text, confidence = engine.recognize(image, message["languages"])
            response = {"id": message["id"], "text": text, "confidence": confidence}
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
    serve(engine)
