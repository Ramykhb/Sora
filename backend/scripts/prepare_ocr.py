"""Download official lightweight PaddleOCR v5 detection and recognition models."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

MODELS = {
    "detection": "PP-OCRv5_mobile_det",
    "english": "en_PP-OCRv5_mobile_rec",
    "latin_french": "latin_PP-OCRv5_mobile_rec",
    "arabic": "arabic_PP-OCRv5_mobile_rec",
}
BASE_URL = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "models" / "paddleocr"


def prepare_model(directory, purpose, name):
    target = directory / f"{name}_infer"
    required = ("inference.json", "inference.pdiparams", "inference.yml")
    url = f"{BASE_URL}/{name}_infer.tar"
    if not all((target / filename).is_file() for filename in required):
        print(f"Downloading {name}...", flush=True)
        archive = directory / f"{name}.tar.part"
        offset = archive.stat().st_size if archive.exists() else 0
        request = Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urlopen(request, timeout=120) as response:
            mode = "ab" if offset and response.status == 206 else "wb"
            with archive.open(mode) as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        with tarfile.open(archive) as model_archive:
            model_archive.extractall(directory, filter="data")
        archive.unlink()
    if not all((target / filename).is_file() for filename in required):
        raise RuntimeError(f"Model archive is incomplete: {target}")
    files = {}
    for filename in required:
        path = target / filename
        with path.open("rb") as content:
            checksum = hashlib.file_digest(content, "sha256").hexdigest()
        files[filename] = {"bytes": path.stat().st_size, "sha256": checksum}
    print(f"Ready: {name}", flush=True)
    return purpose, {"model": name, "directory": target.name, "source": url, "files": files}


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(prepare_model, directory, purpose, name) for purpose, name in MODELS.items()]
        manifest = dict(future.result() for future in futures)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def install_runtime(directory):
    runtime = directory / ".venv"
    python = runtime / "bin" / "python"
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(runtime)], check=True)
    requirements = Path(__file__).resolve().parents[1] / "requirements-ocr.txt"
    if not requirements.is_file():
        requirements = directory / "requirements-ocr.txt"
    uv = shutil.which("uv")
    command = ([uv, "pip", "install", "--python", str(python)] if uv else
               [str(python), "-m", "pip", "install"])
    subprocess.run([*command, "-r", str(requirements)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--install-runtime", action="store_true", help="Install the isolated CPU runtime")
    args = parser.parse_args()
    manifest = prepare(args.directory)
    if args.install_runtime:
        install_runtime(args.directory)
    total = sum(file["bytes"] for model in manifest.values() for file in model["files"].values())
    print(f"Prepared {len(manifest)} models ({total / 1024**2:.1f} MiB) in {args.directory}")
