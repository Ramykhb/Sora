"""Reproducible real-service acceptance flow using generated, person-free sign images.

Creates and deletes its own temporary account and sessions. Never prints credentials.
The report separates synthetic recognition checks from human accuracy evaluation.
"""

import argparse
import asyncio
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import secrets
from time import perf_counter

import httpx
from PIL import Image, ImageDraw, ImageFont


def sign_image(text):
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((35, 90, 605, 310), outline="black", width=12)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 68)
    except OSError:
        font = ImageFont.load_default(size=68)
    draw.text((320, 200), text, font=font, anchor="mm", fill="black")
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


async def checked(client, method, path, **kwargs):
    response = await client.request(method, path, **kwargs)
    response.raise_for_status()
    return None if response.status_code == 204 else response.json()


async def video_flow(client, sid, content, *, overview=False, overview_question="What is in front of me?"):
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from av import VideoFrame
    import numpy as np

    base = f"/sessions/{sid}/stream"
    config = await checked(client, "GET", base + "/config")
    ice = RTCConfiguration(iceServers=[RTCIceServer(**item) for item in config["ice_servers"]])
    publisher, viewer = RTCPeerConnection(ice), RTCPeerConnection(ice)
    pixels = np.asarray(Image.open(BytesIO(content)).convert("RGB"))
    received = asyncio.get_running_loop().create_future()

    class SignTrack(VideoStreamTrack):
        async def recv(self):
            pts, time_base = await self.next_timestamp()
            frame = VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts, frame.time_base = pts, time_base
            return frame

    @viewer.on("track")
    def on_track(track):
        if not received.done():
            received.set_result(track)

    try:
        publisher.addTrack(SignTrack())
        await publisher.setLocalDescription(await publisher.createOffer())
        answer = await checked(client, "POST", base + "/offer", json={
            "sdp": publisher.localDescription.sdp, "type": "offer",
        })
        await publisher.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
        viewer.addTransceiver("video", direction="recvonly")
        await viewer.setLocalDescription(await viewer.createOffer())
        answer = await checked(client, "POST", base + "/viewer/offer", json={
            "sdp": viewer.localDescription.sdp, "type": "offer",
        })
        await viewer.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
        track = await asyncio.wait_for(received, 30)
        await asyncio.wait_for(track.recv(), 30)
        count, start, observations = 1, perf_counter(), []
        while perf_counter() - start < 3:
            await asyncio.wait_for(track.recv(), 5)
            count += 1
            if count % 10 == 0:
                status = await checked(client, "GET", base + "/status")
                if status.get("observation"):
                    observations.append(status["observation"])
        status = await checked(client, "GET", base + "/status")
        assert count >= 15, "Dashboard viewer did not receive continuous video"
        assert status["frames_received"] > status["frames_sampled"]
        assert observations, "No fresh object observations reached the status API"
        duration = round(perf_counter() - start, 2)
        initial_count = count
        # Keep receiving while the question runs; verify that deduplication of
        # the stationary sign cannot leave the current-view request without a
        # freshly timestamped camera snapshot.
        question_start = perf_counter()
        question_task = asyncio.create_task(checked(client, "POST", f"/sessions/{sid}/questions", json={
            "question": overview_question if overview else "What is written on the current sign?",
            "scope": "recent", "language": "en",
        }))
        try:
            async with asyncio.timeout(45):
                while not question_task.done():
                    await asyncio.wait_for(track.recv(), 5)
                current = await question_task
        finally:
            if not question_task.done():
                question_task.cancel()
                await asyncio.gather(question_task, return_exceptions=True)
        assert current["evidence_frame_ids"], "Current-view answer lacked fresh evidence"
        if overview:
            assert current["uncertain"] and perf_counter() - question_start < 5, "Object overview was not bounded and qualified"
        else:
            assert "123" in current["answer"], "Current-view sign answer lacked correct text"
        return {
            "viewer_frames": initial_count, "duration_s": duration,
            "server_status": status,
            "detection_latency_ms": [item["latency_ms"] for item in observations],
            "current_view_question": {"question": overview_question if overview else "What is written on the current sign?", "answer": current["answer"], "warnings": current["processing_warnings"], "elapsed_ms": round((perf_counter() - question_start) * 1000, 1)},
            "note": "Server receipt-to-observation timing; excludes phone capture, transport and speech onset.",
        }
    finally:
        await publisher.close()
        await viewer.close()
        await checked(client, "DELETE", base)


async def run(args):
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(), "checks": {},
        "dataset": "One generated text sign; no people or external media." if args.overview_only else "Two generated text signs; no people or external media.",
        "mode": "live_overview" if args.overview_only else "full_workflow",
        "limitations": "Synthetic functional checks do not establish real-world obstacle recall, factual answer accuracy, accessibility or iPhone speech latency.",
    }
    password = secrets.token_urlsafe(24)
    email = f"acceptance-{secrets.token_hex(8)}@example.com"
    registered, sid, success = False, None, False
    async with httpx.AsyncClient(base_url=args.url.rstrip("/") + "/api/v1", timeout=300) as client:
        try:
            await checked(client, "POST", "/auth/register", json={
                "email": email, "password": password, "display_name": "Synthetic acceptance test",
            })
            registered = True
            tokens = await checked(client, "POST", "/auth/login", json={"email": email, "password": password})
            client.headers["Authorization"] = "Bearer " + tokens["access_token"]
            session = await checked(client, "POST", "/sessions", json={"consent": True, "alerts_enabled": True})
            sid = session["id"]
            base = f"/sessions/{sid}"
            print("Checking WebRTC publisher, viewer and live observations…", flush=True)
            report["checks"]["video"] = await video_flow(client, sid, sign_image("EXIT 123"), overview=args.overview_only, overview_question=args.overview_question)
            if args.overview_only:
                success = True
                return
            images = []
            report["checks"]["images"] = images
            for text in ["EXIT 123", "ROOM 215"]:
                print("Checking OCR, detection, storage and AI enrichment:", text, flush=True)
                content = sign_image(text)
                start = perf_counter()
                result = await checked(client, "POST", base + "/frames", files={"image": ("sign.jpg", content)}, data={"force": "true"})
                frame = result["frame"]
                assert not {"vision_unavailable", "embedding_unavailable"}.intersection(frame["processing_warnings"]), "Real AI inference failed"
                images.append({"expected_text": text, "ocr_text": frame["ocr_text"], "caption": frame["caption"], "elapsed_ms": round((perf_counter() - start) * 1000, 1)})
                assert all(token in frame["ocr_text"].upper() for token in text.split()), "Synthetic sign OCR did not match"
                duplicate = await checked(client, "POST", base + "/frames", files={"image": ("sign.jpg", content)})
                assert duplicate["reason"] == "duplicate"
                response = await client.get(base + f"/frames/{frame['id']}/image")
                response.raise_for_status()
                assert response.content.startswith(b"\xff\xd8")
            searches = []
            print("Checking semantic memory retrieval…", flush=True)
            for query, expected in [("exit sign", "EXIT"), ("room number", "215")]:
                result = await checked(client, "GET", base + "/frames/search", params={"q": query})
                assert not result["warnings"], "Semantic retrieval dependency failed"
                assert any(expected in frame["ocr_text"] for frame in result["frames"])
                searches.append({"query": query, "expected_in_top_k": True, "k": len(result["frames"])})
            report["checks"]["search"] = searches
            answers = []
            report["checks"]["answers"] = answers
            for language, question, terms in [
                ("en", "What number was written after ROOM?", ["215"]),
                ("fr", "Quel nombre était écrit après ROOM ?", ["215"]),
            ]:
                print("Checking grounded answer and spoken WAV:", language, flush=True)
                start = perf_counter()
                answer = await checked(client, "POST", base + "/questions", json={"question": question, "scope": "memory", "language": language})
                record = {"language": language, "question": question, "answer": answer["answer"], "uncertain": answer["uncertain"], "warnings": answer["processing_warnings"], "expected_term_match": all(term in answer["answer"] for term in terms), "answer_ms": round((perf_counter() - start) * 1000, 1)}
                answers.append(record)
                assert not {"vision_unavailable", "embedding_unavailable"}.intersection(answer["processing_warnings"]), "Answer inference dependency failed: " + str(answer["processing_warnings"])
                assert answer["evidence_frame_ids"], "Answer did not cite retained evidence"
                spoken = await client.get(base + f"/questions/{answer['id']}/audio")
                spoken.raise_for_status()
                assert spoken.content.startswith(b"RIFF")
                await checked(client, "POST", base + f"/questions/{answer['id']}/feedback", json={"rating": "unsure", "notes": "Automated synthetic check; human review still required."})
                record.update(elapsed_ms=round((perf_counter() - start) * 1000, 1), wav_bytes=len(spoken.content))
            print("Checking speech recognition and voice-question flow…", flush=True)
            audio = await client.post("/speech/synthesis", json={"text": "What number was written after ROOM?", "language": "en"})
            audio.raise_for_status()
            voice = await checked(client, "POST", base + "/questions/audio", files={"audio": ("question.wav", audio.content, "audio/wav")}, data={"language": "en", "scope": "memory"})
            assert voice["question"] and voice["evidence_frame_ids"]
            report["checks"]["voice"] = {"recognized_question": voice["question"], "answer": voice["answer"]}
            history = await checked(client, "GET", base + "/questions")
            assert len(history) == 4
            report["checks"]["history_count"] = len(history)
            await checked(client, "DELETE", base)
            assert (await client.get(base + "/frames")).status_code == 404
            sid = None
            report["checks"]["session_deletion"] = True
            success = True
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if sid:
                try:
                    await checked(client, "DELETE", f"/sessions/{sid}")
                except Exception:
                    report["cleanup_session_failed"] = True
            if registered:
                try:
                    if "Authorization" not in client.headers:
                        tokens = await checked(client, "POST", "/auth/login", json={"email": email, "password": password})
                        client.headers["Authorization"] = "Bearer " + tokens["access_token"]
                    await checked(client, "DELETE", "/auth/me", json={"password": password})
                    report["temporary_account_deleted"] = True
                except Exception:
                    report["cleanup_account_failed"] = True
            report["passed"] = success
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print("Acceptance report:", args.output, "passed:", success)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("acceptance-report.json"))
    parser.add_argument("--overview-only", action="store_true", help="Check live streaming and a fast object overview, then clean up")
    parser.add_argument("--overview-question", default="What is in front of me?", help="Question wording for --overview-only")
    asyncio.run(run(parser.parse_args()))
