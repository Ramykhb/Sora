"""Evaluate a consented fixture set against the running backend; retain detailed evidence."""

import argparse
import json
from pathlib import Path
import statistics
from time import perf_counter
import httpx
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", help="Registered account email; password is prompted securely")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("evaluation-report.json"))
    parser.add_argument("--keep-session", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    report = {"images": [], "questions": []}
    image_ids = {}
    latencies = []
    with httpx.Client(
        base_url=args.url.rstrip("/") + settings.api_prefix,
        timeout=300,
    ) as client:
        from getpass import getpass

        email = args.email or input("Account email: ").strip()
        response = client.post(
            "/auth/login", json={"email": email, "password": getpass("Password: ")}
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        response = client.post(
            "/sessions", json={"consent": True, "language": manifest.get("language", "en")}
        )
        response.raise_for_status()
        sid = response.json()["id"]
        report["session_id"] = sid
        base = f"/sessions/{sid}"
        try:
            for sample in manifest.get("images", []):
                path = (args.manifest.parent / sample["path"]).resolve()
                with path.open("rb") as file:
                    start = perf_counter()
                    response = client.post(
                        base + "/frames", files={"image": (path.name, file)}, data={"force": "true"}
                    )
                    response.raise_for_status()
                    latency = (perf_counter() - start) * 1000
                result = response.json()["frame"]
                image_ids[sample["path"]] = result["id"]
                expected = sample.get("expected_text", "").casefold().split()
                labels = {obj["label"] for obj in result["detected_objects"]}
                objects = sample.get("expected_objects", [])
                report["images"].append(
                    {
                        "path": sample["path"],
                        "frame_id": result["id"],
                        "latency_ms": latency,
                        "ocr_text": result["ocr_text"],
                        "ocr_token_recall": sum(
                            x in result["ocr_text"].casefold() for x in expected
                        )
                        / len(expected)
                        if expected
                        else None,
                        "object_recall": sum(x in labels for x in objects) / len(objects)
                        if objects
                        else None,
                        "warnings": result["processing_warnings"],
                    }
                )
            for sample in manifest.get("questions", []):
                start = perf_counter()
                response = client.post(
                    base + "/questions",
                    json={
                        "question": sample["question"],
                        "language": sample.get("language", manifest.get("language", "en")),
                        "scope": "memory",
                    },
                )
                response.raise_for_status()
                latency = (perf_counter() - start) * 1000
                latencies.append(latency)
                result = response.json()
                response = client.get(base + "/frames/search", params={"q": sample["question"]})
                response.raise_for_status()
                retrieved = {item["id"] for item in response.json()["frames"]}
                expected_ids = {image_ids[p] for p in sample.get("relevant_images", [])}
                terms = sample.get("expected_answer_terms", [])
                report["questions"].append(
                    {
                        **result,
                        "measured_latency_ms": latency,
                        "retrieval_recall_at_k": len(retrieved & expected_ids) / len(expected_ids)
                        if expected_ids
                        else None,
                        "answer_term_recall": sum(
                            t.casefold() in result["answer"].casefold() for t in terms
                        )
                        / len(terms)
                        if terms
                        else None,
                    }
                )
            if latencies:
                ordered = sorted(latencies)
                report["latency"] = {
                    "mean_ms": statistics.mean(latencies),
                    "median_ms": statistics.median(latencies),
                    "p95_ms": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
                }
            report["accuracy_note"] = (
                "Answer term recall is a text heuristic, not factual accuracy. Have human reviewers rate correctness and submit feedback."
            )
        finally:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            if not args.keep_session:
                client.delete(base).raise_for_status()
    print("Report written to", args.output)


if __name__ == "__main__":
    main()
