#!/usr/bin/env python3
"""Generate a WAV with Doubao Seed TTS 2.0 and required word timestamps."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import time
import uuid
import wave
from pathlib import Path
from typing import Any

import requests


ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
KEYCHAIN_SERVICE = "codex.ai-self-media-video.DOUBAO_API_KEY"
TIMESTAMP_SCHEMA_VERSION = 1
SENTENCE_ENDINGS = set("。！？!?；;\n")


def load_api_key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value and env_name == "DOUBAO_API_KEY" and platform.system() == "Darwin":
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                getpass.getuser(),
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
    if not value:
        raise SystemExit(
            f"Missing {env_name}. Configure it in a secret-safe environment or macOS "
            f"Keychain service {KEYCHAIN_SERVICE}; never store it in the repository."
        )
    return value


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def decode_events(raw: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    cursor = 0
    events: list[dict[str, Any]] = []
    while cursor < len(raw):
        while cursor < len(raw) and raw[cursor].isspace():
            cursor += 1
        if cursor >= len(raw):
            break
        item, cursor = decoder.raw_decode(raw, cursor)
        if isinstance(item, dict):
            events.append(item)
    return events


def safe_metadata(value: Any, key: str = "") -> Any:
    if key == "data" and isinstance(value, str):
        return {"omittedBase64Chars": len(value)}
    if key == "words" and isinstance(value, list):
        return {"omittedWordItems": len(value)}
    if isinstance(value, dict):
        return {k: safe_metadata(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_metadata(item) for item in value]
    if isinstance(value, str) and len(value) > 20000:
        return value[:20000] + "...[truncated]"
    return value


def split_text(text: str, max_bytes: int) -> list[str]:
    if max_bytes <= 0 or len(text.encode("utf-8")) <= max_bytes:
        return [text]
    if max_bytes < 100:
        raise ValueError("--max-request-bytes must be 0 or at least 100")

    sentences: list[str] = []
    buffer: list[str] = []
    for char in text:
        buffer.append(char)
        if char in SENTENCE_ENDINGS:
            piece = "".join(buffer).strip()
            if piece:
                sentences.append(piece)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = sentence if not current else current + "\n" + sentence
        if len(candidate.encode("utf-8")) <= max_bytes:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(sentence.encode("utf-8")) <= max_bytes:
            current = sentence
            continue
        part = ""
        for char in sentence:
            if part and len((part + char).encode("utf-8")) > max_bytes:
                chunks.append(part)
                part = ""
            part += char
        current = part
    if current:
        chunks.append(current)
    return chunks


def timing_value_seconds(item: dict[str, Any], key: str) -> float:
    value = item.get(key)
    if value is None:
        raise ValueError(f"timestamp item is missing {key}: {item}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"timestamp item has a non-finite {key}: {item}")
    return result


def extract_request_words(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for event in events:
        sentence = event.get("sentence")
        if not isinstance(sentence, dict):
            continue
        for item in sentence.get("words") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("word") or "")
            start_seconds = timing_value_seconds(item, "startTime")
            end_seconds = timing_value_seconds(item, "endTime")
            key = (text, start_seconds, end_seconds)
            if key in seen:
                continue
            seen.add(key)
            words.append(
                {
                    "word": text,
                    "startSeconds": start_seconds,
                    "endSeconds": end_seconds,
                    "confidence": item.get("confidence"),
                    "providerItem": safe_metadata(item),
                }
            )
    words.sort(key=lambda item: (item["startSeconds"], item["endSeconds"]))
    return words


def request_once(
    api_key: str,
    text: str,
    output_suffix: str,
    resource_id: str,
    speaker: str,
    speech_rate: int,
    sample_rate: int,
) -> tuple[bytes, dict[str, Any]]:
    request_id = str(uuid.uuid4())
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": "make-book-video"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": output_suffix.lstrip(".") or "wav",
                "sample_rate": sample_rate,
                "speech_rate": speech_rate,
                "loudness_rate": 0,
                "enable_subtitle": True,
            },
        },
    }
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(ENDPOINT, headers=headers, json=body, timeout=240)
    if response.status_code == 429 or response.status_code >= 500:
        raise requests.HTTPError(f"retryable HTTP {response.status_code}", response=response)
    try:
        events = decode_events(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Doubao returned unreadable data (HTTP {response.status_code})"
        ) from exc

    audio_chunks = [
        base64.b64decode(event["data"])
        for event in events
        if isinstance(event.get("data"), str)
    ]
    provider_error = next(
        (
            event
            for event in events
            if (event.get("code") or event.get("header", {}).get("code"))
            not in (None, 0, 20000000)
        ),
        None,
    )
    if not audio_chunks:
        safe_error = (
            {key: provider_error.get(key) for key in ("code", "message")}
            if provider_error
            else None
        )
        raise RuntimeError(
            f"Doubao produced no audio (HTTP {response.status_code}, error={safe_error})"
        )

    request_words = extract_request_words(events)
    return b"".join(audio_chunks), {
        "requestId": request_id,
        "xTtLogid": response.headers.get("X-Tt-Logid", ""),
        "httpStatus": response.status_code,
        "eventCount": len(events),
        "audioEventCount": len(audio_chunks),
        "audioBase64Chars": sum(
            len(event["data"])
            for event in events
            if isinstance(event.get("data"), str)
        ),
        "textBytes": len(text.encode("utf-8")),
        "words": request_words,
        "metadataEvents": [
            safe_metadata(event)
            for event in events
            if not isinstance(event.get("data"), str)
        ],
    }


def request_with_retry(*args: Any, retries: int) -> tuple[bytes, dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return request_once(*args)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(8, 2 ** (attempt - 1)))
    raise RuntimeError(f"Doubao request failed after {retries} attempts: {last_error}")


def merge_wavs(parts: list[bytes], join_pause_ms: int) -> tuple[bytes, list[int], int, int, int]:
    parameters: tuple[int, int, int, str] | None = None
    pcm_parts: list[bytes] = []
    frame_counts: list[int] = []
    for raw in parts:
        with wave.open(io.BytesIO(raw), "rb") as source:
            current = (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getcomptype(),
            )
            if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
                raise RuntimeError("Timestamped narration requires uncompressed 16-bit WAV")
            if parameters is None:
                parameters = current
            elif current != parameters:
                raise RuntimeError("Doubao returned incompatible WAV parameters")
            pcm = source.readframes(source.getnframes())
            pcm_parts.append(pcm)
            # Doubao's streamed WAV may retain a 0xFFFFFFFF-sized placeholder
            # in its header. Count the returned PCM bytes instead of trusting
            # getnframes(), which can otherwise look like a ~24-hour file.
            frame_counts.append(len(pcm) // (current[0] * current[1]))
    if parameters is None:
        raise RuntimeError("No WAV data was returned")

    channels, sample_width, sample_rate, _ = parameters
    silence_frames = round(sample_rate * join_pause_ms / 1000)
    silence = b"\x00" * silence_frames * channels * sample_width
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(sample_rate)
        target.writeframes(silence.join(pcm_parts))
    return output.getvalue(), frame_counts, sample_rate, channels, sample_width


def validate_words(words: list[dict[str, Any]], audio_duration_ms: float) -> None:
    if not words:
        raise RuntimeError(
            "Doubao returned no sentence.words although enable_subtitle=true; "
            "verify that the resource is Seed TTS 2.0."
        )
    previous_start = -1.0
    previous_end = -1.0
    for item in words:
        start = float(item["startMs"])
        end = float(item["endMs"])
        if not math.isfinite(start) or not math.isfinite(end):
            raise RuntimeError(f"Non-finite provider timestamp: {item}")
        if start < 0 or end < start:
            raise RuntimeError(f"Invalid provider timestamp: {item}")
        if start + 0.001 < previous_start or end + 0.001 < previous_end:
            raise RuntimeError(f"Non-monotonic provider timestamp: {item}")
        previous_start, previous_end = start, end
    if words[-1]["endMs"] > audio_duration_ms + 150:
        raise RuntimeError(
            f"Last provider timestamp {words[-1]['endMs']:.3f}ms exceeds "
            f"audio duration {audio_duration_ms:.3f}ms"
        )


def actual_wav_info(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as source:
        pcm = source.readframes(source.getnframes())
        frame_width = source.getnchannels() * source.getsampwidth()
        frames = len(pcm) // frame_width
        return {
            "audioDurationMs": round(frames * 1000 / source.getframerate(), 3),
            "sampleRate": source.getframerate(),
            "channels": source.getnchannels(),
            "sampleWidthBytes": source.getsampwidth(),
        }


def compact_provider_requests(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in requests:
        copy = {
            key: value
            for key, value in item.items()
            if key not in {"words", "metadataEvents"}
        }
        copy["wordCount"] = int(item.get("wordCount") or len(item.get("words") or []))
        copy["metadataEventCount"] = int(
            item.get("metadataEventCount") or len(item.get("metadataEvents") or [])
        )
        compacted.append(copy)
    return compacted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--resource-id", default=os.environ.get("DOUBAO_TTS_RESOURCE_ID", ""))
    parser.add_argument("--speaker", default=os.environ.get("DOUBAO_TTS_SPEAKER", ""))
    parser.add_argument("--speech-rate", type=int, default=20)
    parser.add_argument("--sample-rate", type=int, default=24000)
    parser.add_argument("--api-key-env", default="DOUBAO_API_KEY")
    parser.add_argument("--max-request-bytes", type=int, default=0)
    parser.add_argument("--join-pause-ms", type=int, default=180)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        raise SystemExit("Narration text is empty")
    if args.output.suffix.lower() != ".wav":
        raise SystemExit("--output must be a .wav file")
    if not args.resource_id.strip() or not args.speaker.strip():
        raise SystemExit("--resource-id and --speaker are required")
    if not -50 <= args.speech_rate <= 100:
        raise SystemExit("--speech-rate must be between -50 and 100")
    if not 0 <= args.join_pause_ms <= 3000:
        raise SystemExit("--join-pause-ms must be between 0 and 3000")

    chunks = split_text(text, args.max_request_bytes)
    effective_pause = 0 if len(chunks) == 1 else args.join_pause_ms
    cache_payload = {
        "schemaVersion": TIMESTAMP_SCHEMA_VERSION,
        "endpoint": ENDPOINT,
        "text": text,
        "resourceId": args.resource_id,
        "speaker": args.speaker,
        "speechRate": args.speech_rate,
        "sampleRate": args.sample_rate,
        "maxRequestBytes": args.max_request_bytes,
        "joinPauseMs": effective_pause,
        "enableSubtitle": True,
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    report_path = args.report or args.output.with_suffix(args.output.suffix + ".json")
    if args.output.is_file() and report_path.is_file() and not args.force:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        if existing.get("cacheKey") == cache_key and args.output.stat().st_size > 44:
            actual_audio_sha = bytes_sha256(args.output.read_bytes())
            if existing.get("audioSha256") != actual_audio_sha:
                raise SystemExit(
                    "Cached WAV does not match its TTS report. Inspect the files and use "
                    "--force only when a paid regeneration is intended."
                )
            wav_info = actual_wav_info(args.output)
            existing.update(wav_info)
            validate_words(existing.get("timestamps", {}).get("words") or [], wav_info["audioDurationMs"])
            existing["providerRequests"] = compact_provider_requests(
                existing.get("providerRequests") or []
            )
            existing["cacheHit"] = True
            existing["cacheReportRevalidated"] = True
            report_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(existing, ensure_ascii=False, indent=2))
            return 0

    api_key = load_api_key(args.api_key_env)
    raw_parts: list[bytes] = []
    request_reports: list[dict[str, Any]] = []
    for chunk in chunks:
        audio, request_report = request_with_retry(
            api_key,
            chunk,
            args.output.suffix,
            args.resource_id,
            args.speaker,
            args.speech_rate,
            args.sample_rate,
            retries=args.retries,
        )
        raw_parts.append(audio)
        request_reports.append(request_report)

    merged, frame_counts, actual_rate, channels, sample_width = merge_wavs(
        raw_parts, effective_pause
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(merged)

    join_frames = round(actual_rate * effective_pause / 1000)
    offset_frames = 0
    words: list[dict[str, Any]] = []
    for request_index, (request_report, frame_count) in enumerate(
        zip(request_reports, frame_counts), start=1
    ):
        offset_ms = offset_frames * 1000 / actual_rate
        for item in request_report["words"]:
            words.append(
                {
                    "key": f"word-{len(words) + 1:04d}",
                    "word": item["word"],
                    "startMs": round(offset_ms + item["startSeconds"] * 1000, 3),
                    "endMs": round(offset_ms + item["endSeconds"] * 1000, 3),
                    "confidence": item.get("confidence"),
                    "requestIndex": request_index,
                    "providerStartSeconds": item["startSeconds"],
                    "providerEndSeconds": item["endSeconds"],
                }
            )
        offset_frames += frame_count
        if request_index < len(frame_counts):
            offset_frames += join_frames

    audio_duration_ms = offset_frames * 1000 / actual_rate
    validate_words(words, audio_duration_ms)
    result = {
        "version": 1,
        "status": "verified-provider-word-timestamps",
        "output": str(args.output),
        "audioBytes": len(merged),
        "audioSha256": bytes_sha256(merged),
        "audioDurationMs": round(audio_duration_ms, 3),
        "sampleRate": actual_rate,
        "channels": channels,
        "sampleWidthBytes": sample_width,
        "cacheKey": cache_key,
        "cacheHit": False,
        "provider": "doubao-direct-v3",
        "endpoint": ENDPOINT,
        "resourceId": args.resource_id,
        "speaker": args.speaker,
        "speechRate": args.speech_rate,
        "enableSubtitle": True,
        "requestMode": "single" if len(chunks) == 1 else "chunked",
        "providerRequestCount": len(chunks),
        "chunkTextBytes": [len(chunk.encode("utf-8")) for chunk in chunks],
        "joinPauseMs": effective_pause,
        "edgeSilenceTrimmed": False,
        "timestamps": {
            "source": "Doubao V3 sentence.words",
            "level": "provider-word-or-character",
            "unit": "milliseconds",
            "count": len(words),
            "words": words,
        },
        "xTtLogids": [
            item["xTtLogid"] for item in request_reports if item.get("xTtLogid")
        ],
        "providerRequests": compact_provider_requests(request_reports),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
