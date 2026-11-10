"""Load downloaded PaddleOCR models and run a small local CPU smoke check."""
import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from scripts.prepare_ocr import DEFAULT_DIRECTORY, MODELS


def check(directory):
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from paddleocr import TextDetection, TextRecognition

    font = ImageFont.truetype("DejaVuSans.ttf", 52)
    samples = {"english": "EXIT 123", "latin_french": "Entrée principale", "arabic": "مخرج 123"}
    report = {}
    options = {"device": "cpu", "cpu_threads": 2, "enable_mkldnn": False}
    for purpose, name in MODELS.items():
        path = directory / f"{name}_infer"
        model_type = TextDetection if purpose == "detection" else TextRecognition
        model = model_type(model_name=name, model_dir=str(path), **options)
        text = samples.get(purpose, "EXIT 123")
        direction = "rtl" if purpose == "arabic" else "ltr"
        size = font.getbbox(text, direction=direction)
        image = Image.new("RGB", (size[2] - size[0] + 48, 110), "white")
        ImageDraw.Draw(image).text((24, 12), text, fill="black", font=font, direction=direction)
        image.save(directory / f"check_{purpose}.png")
        pixels = np.asarray(image)
        result = next(iter(model.predict(pixels)))
        started = perf_counter()
        result = next(iter(model.predict(pixels)))
        entry = {"model": name, "warm_ms": round((perf_counter() - started) * 1000, 1)}
        if purpose == "detection":
            entry["text_regions"] = len(result["dt_polys"])
            if not entry["text_regions"]:
                raise RuntimeError("Text detector did not find the generated text")
        else:
            entry.update(expected=text, recognized=result["rec_text"], confidence=float(result["rec_score"]))
            if purpose == "english" and "EXIT" not in entry["recognized"].upper():
                raise RuntimeError("English recognizer did not recognize the generated EXIT sample")
        report[purpose] = entry
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        del model
    (directory / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    check(args.directory)
