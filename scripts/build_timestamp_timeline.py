#!/usr/bin/env python3
"""Align scenes and caption cards to Doubao provider timestamps and build final PCM audio."""

from __future__ import annotations

import array
import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import textwrap
import unicodedata
import wave
from pathlib import Path
from typing import Any


def normalized_chars(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in text if unicodedata.category(char)[:1] in {"L", "N"})


def first_difference(left: str, right: str) -> dict[str, Any]:
    index = 0
    limit = min(len(left), len(right))
    while index < limit and left[index] == right[index]:
        index += 1
    return {
        "index": index,
        "sourceSnippet": left[max(0, index - 16):index + 32],
        "providerSnippet": right[max(0, index - 16):index + 32],
        "sourceLength": len(left),
        "providerLength": len(right),
    }


def require_same_text(label: str, source: str, provider: str) -> None:
    if source != provider:
        difference = first_difference(source, provider)
        raise SystemExit(
            f"{label} does not match provider-normalized text: "
            + json.dumps(difference, ensure_ascii=False)
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Replace a generated text artifact only after its bytes are durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    atomic_write_text(
        path, json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    )


def project_relative(path: Path, project: Path, label: str) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"{label} must be inside the project: {resolved}") from exc


def required_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit(f"{label} must be an integer")
    return value


def validate_provider_evidence(
    tts_report: dict[str, Any],
    audio_path: Path,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile provider evidence with the raw WAV, case voice, and narration.

    This function is intentionally reusable by final QA.  The timeline builder
    must not turn copied report fields into trusted alignment metadata without
    reopening and reconciling their source artifacts.
    """
    if tts_report.get("provider") != "doubao-direct-v3":
        raise SystemExit("TTS report provider must be doubao-direct-v3")
    if tts_report.get("status") != "verified-provider-word-timestamps":
        raise SystemExit("TTS report status is not verified-provider-word-timestamps")
    if sha256(audio_path) != str(tts_report.get("audioSha256") or ""):
        raise SystemExit("Raw narration WAV hash differs from TTS report audioSha256")

    voice = case.get("voice") or {}
    if not isinstance(voice, dict):
        raise SystemExit("case.voice must be an object")
    for field in ("resourceId", "speaker"):
        expected = str(voice.get(field) or "").strip()
        actual = str(tts_report.get(field) or "").strip()
        if not expected:
            raise SystemExit(f"case.voice.{field} is required")
        if actual != expected:
            raise SystemExit(f"TTS report {field} differs from case.voice.{field}")
    expected_rate = required_integer(voice.get("speechRate"), "case.voice.speechRate")
    report_rate = required_integer(tts_report.get("speechRate"), "TTS report speechRate")
    if report_rate != expected_rate:
        raise SystemExit("TTS report speechRate differs from case.voice.speechRate")
    if voice.get("enableSubtitle") is not True:
        raise SystemExit("case.voice.enableSubtitle must be true")
    if tts_report.get("enableSubtitle") is not True:
        raise SystemExit("TTS report does not prove enableSubtitle=true")
    if voice.get("requireSingleProviderRequest") is not True:
        raise SystemExit("case.voice.requireSingleProviderRequest must be true")
    if tts_report.get("requestMode") != "single":
        raise SystemExit("TTS report requestMode must be single")
    request_count = required_integer(
        tts_report.get("providerRequestCount"), "TTS report providerRequestCount"
    )
    attempt_count = required_integer(
        tts_report.get("providerAttemptCount"), "TTS report providerAttemptCount"
    )
    if request_count != 1:
        raise SystemExit("TTS report providerRequestCount must be exactly 1")
    if attempt_count != 1:
        raise SystemExit("TTS report providerAttemptCount must be exactly 1")

    logids = tts_report.get("xTtLogids")
    if (
        not isinstance(logids, list)
        or not logids
        or any(not isinstance(value, str) or not value.strip() for value in logids)
    ):
        raise SystemExit("TTS report xTtLogids must contain provider log IDs")
    if len(set(logids)) != len(logids):
        raise SystemExit("TTS report xTtLogids contains duplicates")

    provider_requests = tts_report.get("providerRequests")
    if not isinstance(provider_requests, list) or len(provider_requests) != request_count:
        raise SystemExit(
            "TTS report providerRequests must match providerRequestCount"
        )
    request_logids: list[str] = []
    counted_attempts = 0
    for index, request in enumerate(provider_requests, start=1):
        if not isinstance(request, dict):
            raise SystemExit(f"TTS provider request {index} must be an object")
        if not str(request.get("requestId") or "").strip():
            raise SystemExit(f"TTS provider request {index} has no requestId")
        request_http_status = required_integer(
            request.get("httpStatus"),
            f"TTS provider request {index} httpStatus",
        )
        if request_http_status != 200:
            raise SystemExit(f"TTS provider request {index} httpStatus must be 200")
        logid = str(request.get("xTtLogid") or "").strip()
        if not logid:
            raise SystemExit(f"TTS provider request {index} has no xTtLogid")
        request_logids.append(logid)
        current_attempts = required_integer(
            request.get("attemptCount"),
            f"TTS provider request {index} attemptCount",
        )
        attempts = request.get("attempts")
        if not isinstance(attempts, list) or len(attempts) != current_attempts:
            raise SystemExit(
                f"TTS provider request {index} attempts do not match attemptCount"
            )
        if current_attempts != 1:
            raise SystemExit(f"TTS provider request {index} must have one HTTP attempt")
        attempt = attempts[0]
        if not isinstance(attempt, dict) or attempt.get("status") != "succeeded":
            raise SystemExit(f"TTS provider request {index} has no successful attempt")
        attempt_http_status = required_integer(
            attempt.get("httpStatus"),
            f"TTS provider request {index} attempt httpStatus",
        )
        if attempt_http_status != 200:
            raise SystemExit(
                f"TTS provider request {index} attempt httpStatus must be 200"
            )
        attempt_number = required_integer(
            attempt.get("attempt"),
            f"TTS provider request {index} attempt number",
        )
        if attempt_number != 1:
            raise SystemExit(f"TTS provider request {index} attempt number must be 1")
        if str(attempt.get("requestId") or "") != str(request.get("requestId") or ""):
            raise SystemExit(f"TTS provider request {index} attempt requestId differs")
        if str(attempt.get("xTtLogid") or "") != logid:
            raise SystemExit(f"TTS provider request {index} attempt log ID differs")
        counted_attempts += current_attempts
    if request_logids != logids:
        raise SystemExit("TTS report xTtLogids differ from providerRequests")
    if counted_attempts != attempt_count:
        raise SystemExit("TTS provider attempt records differ from providerAttemptCount")

    timestamp_block = tts_report.get("timestamps")
    if not isinstance(timestamp_block, dict):
        raise SystemExit("TTS report timestamps must be an object")
    if timestamp_block.get("source") != "Doubao V3 sentence.words":
        raise SystemExit("TTS report timestamp source is not Doubao V3 sentence.words")
    words = timestamp_block.get("words")
    if not isinstance(words, list) or not words:
        raise SystemExit("TTS report timestamps.words is empty")
    timestamp_count = required_integer(
        timestamp_block.get("count"), "TTS report timestamps.count"
    )
    if timestamp_count != len(words):
        raise SystemExit("TTS report timestamps.count differs from timestamps.words")
    seen_keys: set[str] = set()
    previous_start = -1.0
    previous_end = -1.0
    for index, item in enumerate(words, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"TTS timestamp word {index} must be an object")
        key = str(item.get("key") or "").strip()
        if not key or key in seen_keys:
            raise SystemExit(f"TTS timestamp word {index} has a missing or duplicate key")
        expected_key = f"word-{index:04d}"
        if key != expected_key:
            raise SystemExit(
                f"TTS timestamp word {index} key must be {expected_key}, got {key}"
            )
        seen_keys.add(key)
        if not str(item.get("word") or ""):
            raise SystemExit(f"TTS timestamp word {index} has no text")
        start = float(item.get("startMs"))
        end = float(item.get("endMs"))
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise SystemExit(f"TTS timestamp word {index} has an invalid range")
        if start + 0.001 < previous_start or end + 0.001 < previous_end:
            raise SystemExit(f"TTS timestamp word {index} is not monotonic")
        request_index = required_integer(
            item.get("requestIndex"), f"TTS timestamp word {index} requestIndex"
        )
        if request_index != 1:
            raise SystemExit(f"TTS timestamp word {index} references another request")
        previous_start, previous_end = start, end

    for index, request in enumerate(provider_requests, start=1):
        reported_word_count = required_integer(
            request.get("wordCount"),
            f"TTS provider request {index} wordCount",
        )
        actual_word_count = sum(
            1 for item in words if item.get("requestIndex") == index
        )
        if reported_word_count != actual_word_count:
            raise SystemExit(
                f"TTS provider request {index} wordCount differs from timestamps.words"
            )

    with wave.open(str(audio_path), "rb") as source:
        if source.getcomptype() != "NONE" or source.getsampwidth() != 2:
            raise SystemExit("Raw narration must be uncompressed 16-bit PCM WAV")
        audio_frames = source.getnframes()
        audio_rate = source.getframerate()
        audio_channels = source.getnchannels()
        audio_width = source.getsampwidth()
    duration_ms = audio_frames * 1000 / audio_rate
    if abs(duration_ms - float(tts_report.get("audioDurationMs") or 0)) > 2:
        raise SystemExit("Raw narration duration differs from TTS report")
    if required_integer(tts_report.get("sampleRate"), "TTS report sampleRate") != audio_rate:
        raise SystemExit("Raw narration sample rate differs from TTS report")
    if voice.get("sampleRate") is not None and required_integer(
        voice.get("sampleRate"), "case.voice.sampleRate"
    ) != audio_rate:
        raise SystemExit("Raw narration sample rate differs from case.voice.sampleRate")
    if required_integer(tts_report.get("channels"), "TTS report channels") != audio_channels:
        raise SystemExit("Raw narration channel count differs from TTS report")
    if required_integer(
        tts_report.get("sampleWidthBytes"), "TTS report sampleWidthBytes"
    ) != audio_width:
        raise SystemExit("Raw narration sample width differs from TTS report")
    if float(words[-1]["endMs"]) > duration_ms + 150:
        raise SystemExit("Last TTS timestamp exceeds the raw narration duration")

    segments = load_segments(case)
    source_stream = "".join(segment["normalized"] for segment in segments)
    timed_chars = expand_timed_chars(words)
    provider_stream = "".join(item["char"] for item in timed_chars)
    require_same_text("Full case narration", source_stream, provider_stream)
    return {
        "timestampBlock": timestamp_block,
        "timedChars": timed_chars,
        "segments": segments,
        "audioDurationMs": duration_ms,
    }


def pcm_region_rms_dbfs(
    samples: array.array, channels: int, start_frame: int, end_frame: int
) -> float:
    start = max(0, start_frame * channels)
    end = min(len(samples), end_frame * channels)
    count = end - start
    if count <= 0:
        return -120.0
    square_sum = sum(int(value) * int(value) for value in samples[start:end])
    rms = math.sqrt(square_sum / count)
    if rms <= 0:
        return -120.0
    return max(-120.0, 20 * math.log10(rms / 32767))


def find_safe_pcm_silence(
    pcm: bytes,
    *,
    channels: int,
    sample_rate: int,
    search_start_ms: float,
    search_end_ms: float,
    threshold_dbfs: float = -38.0,
    analysis_window_ms: float = 10.0,
    minimum_silence_ms: float = 120.0,
    guard_ms: float = 80.0,
) -> dict[str, Any]:
    """Find a sample-safe insertion point inside verified PCM silence."""
    if search_end_ms <= search_start_ms:
        raise SystemExit("PCM silence search range is empty")

    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    total_frames = len(samples) // channels
    start_frame = max(0, round(search_start_ms * sample_rate / 1000))
    end_frame = min(total_frames, round(search_end_ms * sample_rate / 1000))
    window_frames = max(1, round(analysis_window_ms * sample_rate / 1000))

    intervals: list[tuple[int, int]] = []
    quiet_start: int | None = None
    cursor = start_frame
    while cursor < end_frame:
        stop = min(end_frame, cursor + window_frames)
        quiet = pcm_region_rms_dbfs(samples, channels, cursor, stop) <= threshold_dbfs
        if quiet and quiet_start is None:
            quiet_start = cursor
        elif not quiet and quiet_start is not None:
            intervals.append((quiet_start, cursor))
            quiet_start = None
        cursor = stop
    if quiet_start is not None:
        intervals.append((quiet_start, end_frame))

    minimum_frames = round(minimum_silence_ms * sample_rate / 1000)
    candidates = [item for item in intervals if item[1] - item[0] >= minimum_frames]
    if not candidates:
        raise SystemExit(
            "No acoustic-safe PCM silence found between provider segments: "
            f"{search_start_ms:.3f}-{search_end_ms:.3f}ms at {threshold_dbfs:.1f}dBFS"
        )

    silence_start, silence_end = max(candidates, key=lambda item: item[1] - item[0])
    boundary_frame = round((silence_start + silence_end) / 2)
    guard_frames = round(guard_ms * sample_rate / 1000)
    guard_start = max(silence_start, boundary_frame - guard_frames)
    guard_end = min(silence_end, boundary_frame + guard_frames)
    guard_rms = pcm_region_rms_dbfs(samples, channels, guard_start, guard_end)
    if guard_rms > threshold_dbfs:
        raise SystemExit(
            f"Chosen PCM hold boundary is not quiet enough: {guard_rms:.3f}dBFS"
        )

    return {
        "boundaryMethod": "verified-pcm-silence",
        "rawBoundarySampleFrame": boundary_frame,
        "rawBoundaryMs": round(boundary_frame * 1000 / sample_rate, 3),
        "silenceSearchStartMs": round(search_start_ms, 3),
        "silenceSearchEndMs": round(search_end_ms, 3),
        "silenceStartMs": round(silence_start * 1000 / sample_rate, 3),
        "silenceEndMs": round(silence_end * 1000 / sample_rate, 3),
        "silenceDurationMs": round((silence_end - silence_start) * 1000 / sample_rate, 3),
        "silenceThresholdDbfs": threshold_dbfs,
        "analysisWindowMs": analysis_window_ms,
        "minimumSilenceMs": minimum_silence_ms,
        "guardMs": guard_ms,
        "guardRmsDbfs": round(guard_rms, 3),
    }


def load_segments(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    segments = []
    for item in storyboard.get("segments") or []:
        narration = str(item.get("narration") or item.get("spoken_text") or "").strip()
        if not narration:
            continue
        segment_id = str(item.get("id") or "").strip()
        if not segment_id:
            raise SystemExit("Every narrated segment needs an id")
        normalized = normalized_chars(narration)
        if not normalized:
            raise SystemExit(f"Segment {segment_id} has no alignable narration characters")
        segments.append({**item, "id": segment_id, "narration": narration, "normalized": normalized})
    if not segments:
        raise SystemExit("Storyboard has no narrated segments")
    return segments


def load_caption_document(
    storyboard: dict[str, Any], captions_path: Path | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if captions_path:
        document = json.loads(captions_path.read_text(encoding="utf-8"))
        cards = document.get("cards") or []
        return document, cards

    cards: list[dict[str, Any]] = []
    for segment in storyboard.get("segments") or []:
        for card in segment.get("captions") or []:
            cards.append({**card, "segmentId": segment.get("id")})
    return {"version": 1, "cards": cards}, cards


def expand_timed_chars(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timed_chars: list[dict[str, Any]] = []
    for word_index, item in enumerate(words, start=1):
        text = normalized_chars(str(item.get("word") or ""))
        if not text:
            continue
        start = float(item["startMs"])
        end = float(item["endMs"])
        if end < start:
            raise SystemExit(f"Invalid provider timestamp item: {item}")
        duration = end - start
        source_key = str(item.get("key") or f"word-{word_index:04d}")
        for char_index, char in enumerate(text):
            char_start = start + duration * char_index / len(text)
            char_end = start + duration * (char_index + 1) / len(text)
            timed_chars.append(
                {
                    "key": f"{source_key}-char-{char_index + 1:02d}",
                    "providerWordKey": source_key,
                    "char": char,
                    "rawStartMs": round(char_start, 3),
                    "rawEndMs": round(char_end, 3),
                    "confidence": item.get("confidence"),
                }
            )
    if not timed_chars:
        raise SystemExit("TTS report contains no alignable provider timestamps")
    return timed_chars


def unique_word_keys(chars: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in chars:
        key = item["providerWordKey"]
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def require_provider_item_boundary(
    timed_chars: list[dict[str, Any]], index: int, label: str
) -> None:
    if index <= 0 or index >= len(timed_chars):
        return
    before = timed_chars[index - 1]["providerWordKey"]
    after = timed_chars[index]["providerWordKey"]
    if before == after:
        raise SystemExit(
            f"{label} splits one provider timing item ({before}); merge the caption "
            "or move the boundary instead of interpolating a sub-word cut"
        )


def frame_from_ms(value: float, fps: int) -> int:
    return int(round(value * fps / 1000))


def fit_positive_durations(durations: list[int], target: int, label: str) -> list[int]:
    if target < len(durations):
        raise SystemExit(
            f"{label} has {target} frames for {len(durations)} positive-duration items"
        )
    fitted = [max(1, int(value)) for value in durations]
    difference = target - sum(fitted)
    if difference >= 0:
        fitted[-1] += difference
        return fitted
    remaining = -difference
    for index in range(len(fitted) - 1, -1, -1):
        removable = fitted[index] - 1
        take = min(removable, remaining)
        fitted[index] -= take
        remaining -= take
        if not remaining:
            return fitted
    raise SystemExit(f"{label} cannot fit its positive ranges into {target} frames")


def normalize_frame_ranges(
    scenes: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    total_frames: int,
) -> None:
    """Make scene and caption ranges contiguous and end exactly at total_frames."""
    if not scenes:
        raise SystemExit("Cannot normalize an empty scene timeline")
    raw_durations = [
        int(item.get("endFrame") or 0) - int(item.get("startFrame") or 0)
        for item in scenes
    ]
    hold_total = sum(
        max(1, duration)
        for item, duration in zip(scenes, raw_durations)
        if item.get("kind") == "silent-hold"
    )
    narrated_indexes = [
        index for index, item in enumerate(scenes) if item.get("kind") != "silent-hold"
    ]
    if not narrated_indexes:
        raise SystemExit("Scene timeline must contain at least one narrated scene")
    narrated_target = total_frames - hold_total
    narrated_durations = fit_positive_durations(
        [raw_durations[index] for index in narrated_indexes],
        narrated_target,
        "narrated timeline",
    )
    fitted_by_index = {
        index: duration for index, duration in zip(narrated_indexes, narrated_durations)
    }
    cursor = 0
    scene_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(scenes):
        duration = (
            max(1, raw_durations[index])
            if item.get("kind") == "silent-hold"
            else fitted_by_index[index]
        )
        item["startFrame"] = cursor
        item["endFrame"] = cursor + duration
        cursor += duration
        scene_id = str(item.get("id") or "")
        if item.get("kind") != "silent-hold" and scene_id:
            scene_by_id[scene_id] = item
    if cursor != total_frames:
        raise SystemExit(
            f"Normalized scenes end at frame {cursor}, expected {total_frames}"
        )

    cards_by_segment: dict[str, list[dict[str, Any]]] = {}
    for card in captions:
        cards_by_segment.setdefault(str(card.get("segmentId") or ""), []).append(card)
    for segment_id, cards in cards_by_segment.items():
        scene = scene_by_id.get(segment_id)
        if scene is None:
            raise SystemExit(f"Caption timeline references unknown narrated scene: {segment_id}")
        target = int(scene["endFrame"]) - int(scene["startFrame"])
        durations = fit_positive_durations(
            [
                int(card.get("endFrame") or 0) - int(card.get("startFrame") or 0)
                for card in cards
            ],
            target,
            f"caption timeline for {segment_id}",
        )
        card_cursor = int(scene["startFrame"])
        for card, duration in zip(cards, durations):
            card["startFrame"] = card_cursor
            card["endFrame"] = card_cursor + duration
            card_cursor += duration


def ass_time(frame: int, fps: int) -> str:
    total_cs = round(frame * 100 / fps)
    centiseconds = total_cs % 100
    total_seconds = total_cs // 100
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def wrap_chinese_caption(text: str, max_chars: int) -> list[str]:
    punctuation = set("，。：；！？、；：”》）")
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        paragraph_lines: list[str] = []
        remaining = paragraph.strip()
        while len(remaining) > max_chars:
            split_at = 0
            lower = max(4, max_chars - 7)
            for index in range(max_chars, lower - 1, -1):
                if remaining[index - 1] in punctuation:
                    split_at = index
                    break
            if not split_at:
                split_at = max_chars
            paragraph_lines.append(remaining[:split_at])
            remaining = remaining[split_at:]
        if remaining:
            paragraph_lines.append(remaining)
        normalized: list[str] = []
        for line in paragraph_lines:
            while normalized and line and line[0] in punctuation:
                normalized[-1] += line[0]
                line = line[1:]
            if line:
                normalized.append(line)
        minimum_tail = max(4, max_chars // 2)
        for index in range(len(normalized) - 1, 0, -1):
            current = normalized[index]
            previous = normalized[index - 1]
            if len(current) >= minimum_tail or len(previous) <= minimum_tail:
                continue
            combined = previous + current
            split_at = math.ceil(len(combined) / 2)
            normalized[index - 1] = combined[:split_at]
            normalized[index] = combined[split_at:]
        lines.extend(normalized)
    return lines


def wrap_english_caption(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        lines.extend(
            textwrap.wrap(
                paragraph.strip(),
                width=max_chars,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return [line for line in lines if line]


def ass_lines(lines: list[str]) -> str:
    return r"\N".join(ass_escape(line) for line in lines)


def build_ass(
    cards: list[dict[str, Any]],
    fps: int,
    *,
    width: int = 1080,
    height: int = 1920,
    font: str = "PingFang SC",
    font_size: int = 72,
    english_font_size: int = 40,
    position_y: int = 1500,
) -> str:
    if any(character in font for character in ",\r\n"):
        raise SystemExit("Caption font name cannot contain a comma or newline")
    header = f"""[Script Info]
Title: Provider-timestamped bilingual captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H50000000,-1,0,0,0,100,100,0,0,1,6,1,2,90,90,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    usable_width = max(1, width - 180)
    chinese_max_chars = max(8, int(usable_width / (font_size * 1.02)))
    english_max_chars = max(24, int(usable_width / (english_font_size * 0.58)))
    for card in cards:
        chinese = ass_lines(
            wrap_chinese_caption(
                str(card.get("zhText") or card.get("text") or ""),
                chinese_max_chars,
            )
        )
        english = ass_lines(
            wrap_english_caption(str(card.get("enText") or ""), english_max_chars)
        )
        text = f"{{\\an2\\pos({width // 2},{position_y})}}{chinese}"
        if english:
            text += f"{{\\fs{english_font_size}\\b0}}\\N{english}"
        events.append(
            "Dialogue: 0,"
            f"{ass_time(int(card['startFrame']), fps)},"
            f"{ass_time(int(card['endFrame']), fps)},"
            f"Caption,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--tts-report", type=Path, required=True)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument(
        "--case",
        type=Path,
        help="Approved case.json used to reconcile narration and voice; defaults to --storyboard.",
    )
    parser.add_argument("--captions", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--hold-after")
    parser.add_argument("--hold-frames", type=int, default=0)
    parser.add_argument("--output-audio-name", default="narration.timestamped.final.wav")
    parser.add_argument("--caption-font", default="PingFang SC")
    parser.add_argument("--caption-font-size", type=int, default=72)
    parser.add_argument("--english-font-size", type=int, default=40)
    parser.add_argument("--caption-position-y", type=int, default=1500)
    args = parser.parse_args()

    if args.fps <= 0:
        raise SystemExit("--fps must be positive")
    if args.caption_font_size <= 0 or args.english_font_size <= 0:
        raise SystemExit("Caption font sizes must be positive")
    if bool(args.hold_after) != (args.hold_frames > 0):
        raise SystemExit("--hold-after and a positive --hold-frames must be supplied together")

    case_path = (args.case or args.storyboard).resolve()
    project = case_path.parent
    project_relative(args.storyboard, project, "Storyboard")
    project_relative(args.audio, project, "Raw narration WAV")
    project_relative(args.tts_report, project, "TTS report")
    project_relative(args.output_dir, project, "Timing output directory")
    if args.captions is not None:
        project_relative(args.captions, project, "Caption document")
    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    case = json.loads(case_path.read_text(encoding="utf-8"))
    canvas = storyboard.get("canvas") or {}
    width = int(canvas.get("width") or 1080)
    height = int(canvas.get("height") or 1920)
    if not 0 <= args.caption_position_y <= height:
        raise SystemExit("Caption position must fit inside the canvas")
    tts_report = json.loads(args.tts_report.read_text(encoding="utf-8"))
    segments = load_segments(storyboard)
    provider_evidence = validate_provider_evidence(tts_report, args.audio, case)
    case_stream = "".join(
        segment["normalized"] for segment in provider_evidence["segments"]
    )
    storyboard_stream = "".join(segment["normalized"] for segment in segments)
    require_same_text("Storyboard narration", case_stream, storyboard_stream)
    caption_document, cards = load_caption_document(storyboard, args.captions)
    if not cards:
        raise SystemExit("No caption cards were found")

    timestamp_block = provider_evidence["timestampBlock"]
    timed_chars = provider_evidence["timedChars"]
    source_stream = "".join(segment["normalized"] for segment in segments)
    provider_stream = "".join(item["char"] for item in timed_chars)
    require_same_text("Full narration", source_stream, provider_stream)

    cards_by_segment: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        segment_id = str(card.get("segmentId") or "")
        if not segment_id:
            raise SystemExit(f"Caption card has no segmentId: {card}")
        text = str(card.get("zhText") or card.get("text") or "")
        normalized = normalized_chars(text)
        if not normalized:
            raise SystemExit(f"Caption card has no alignable text: {card.get('id')}")
        card["normalized"] = normalized
        cards_by_segment.setdefault(segment_id, []).append(card)

    segment_spans: dict[str, dict[str, Any]] = {}
    cursor = 0
    for segment in segments:
        segment_cards = cards_by_segment.get(segment["id"], [])
        if not segment_cards:
            raise SystemExit(f"Segment {segment['id']} has no caption cards")
        caption_stream = "".join(card["normalized"] for card in segment_cards)
        require_same_text(
            f"Caption cards for segment {segment['id']}", segment["normalized"], caption_stream
        )
        start_index = cursor
        end_index = cursor + len(segment["normalized"])
        require_provider_item_boundary(
            timed_chars, start_index, f"Segment {segment['id']} start"
        )
        require_provider_item_boundary(
            timed_chars, end_index, f"Segment {segment['id']} end"
        )
        chars = timed_chars[start_index:end_index]
        segment_spans[segment["id"]] = {
            "startIndex": start_index,
            "endIndex": end_index,
            "chars": chars,
            "firstWordStartMs": chars[0]["rawStartMs"],
            "lastWordEndMs": chars[-1]["rawEndMs"],
        }
        card_cursor = start_index
        for card in segment_cards:
            card_end = card_cursor + len(card["normalized"])
            require_provider_item_boundary(
                timed_chars, card_cursor, f"Caption {card.get('id') or 'unknown'} start"
            )
            require_provider_item_boundary(
                timed_chars, card_end, f"Caption {card.get('id') or 'unknown'} end"
            )
            card["_chars"] = timed_chars[card_cursor:card_end]
            card_cursor = card_end
        cursor = end_index

    with wave.open(str(args.audio), "rb") as source:
        params = source.getparams()
        if params.comptype != "NONE" or params.sampwidth != 2:
            raise SystemExit("Input narration must be uncompressed 16-bit PCM WAV")
        pcm = source.readframes(params.nframes)
    if params.framerate % args.fps:
        raise SystemExit("WAV sample rate must be evenly divisible by video fps")
    audio_duration_ms = params.nframes * 1000 / params.framerate
    report_duration = float(tts_report.get("audioDurationMs") or 0)
    if abs(audio_duration_ms - report_duration) > 2:
        raise SystemExit(
            f"WAV duration {audio_duration_ms:.3f}ms differs from TTS report "
            f"{report_duration:.3f}ms"
        )

    raw_boundaries = [0.0]
    for previous, following in zip(segments, segments[1:]):
        previous_end = segment_spans[previous["id"]]["lastWordEndMs"]
        following_start = segment_spans[following["id"]]["firstWordStartMs"]
        if following_start < previous_end:
            raise SystemExit(
                f"Provider timestamps overlap between {previous['id']} and {following['id']}"
            )
        raw_boundaries.append(round((previous_end + following_start) / 2, 3))
    raw_boundaries.append(round(audio_duration_ms, 3))

    holds = list(storyboard.get("timelineHolds") or [])
    if args.hold_after:
        holds.append(
            {
                "id": "cli-hold",
                "afterSegmentId": args.hold_after,
                "durationFrames": args.hold_frames,
                "assets": [],
            }
        )
    hold_by_segment: dict[str, list[dict[str, Any]]] = {}
    segment_ids = {segment["id"] for segment in segments}
    for hold in holds:
        after_id = str(hold.get("afterSegmentId") or "")
        duration_frames = int(hold.get("durationFrames") or 0)
        if duration_frames <= 0:
            continue
        if after_id not in segment_ids:
            raise SystemExit(f"Hold references unknown segment: {after_id}")
        hold_by_segment.setdefault(after_id, []).append({**hold, "durationFrames": duration_frames})

    frame_width = params.nchannels * params.sampwidth
    hold_boundary_evidence: dict[str, dict[str, Any]] = {}
    for index, segment in enumerate(segments):
        segment_id = segment["id"]
        if not hold_by_segment.get(segment_id):
            continue
        if index + 1 >= len(segments):
            raise SystemExit(
                f"Acoustic-safe hold after final narrated segment is unsupported: {segment_id}"
            )
        previous_end = float(segment_spans[segment_id]["lastWordEndMs"])
        following_start = float(
            segment_spans[segments[index + 1]["id"]]["firstWordStartMs"]
        )
        evidence = find_safe_pcm_silence(
            pcm,
            channels=params.nchannels,
            sample_rate=params.framerate,
            search_start_ms=previous_end,
            search_end_ms=following_start,
        )
        evidence["providerMidpointMs"] = raw_boundaries[index + 1]
        raw_boundaries[index + 1] = evidence["rawBoundaryMs"]
        hold_boundary_evidence[segment_id] = evidence

    insertions: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        boundary_ms = raw_boundaries[index + 1]
        for hold in hold_by_segment.get(segment["id"], []):
            evidence = hold_boundary_evidence[segment["id"]]
            insertions.append({**hold, **evidence, "rawBoundaryMs": boundary_ms})
    insertions.sort(key=lambda item: item["rawBoundaryMs"])

    final_pcm = bytearray()
    raw_cursor_frame = 0
    for insertion in insertions:
        boundary_frame = int(insertion["rawBoundarySampleFrame"])
        final_pcm.extend(pcm[raw_cursor_frame * frame_width:boundary_frame * frame_width])
        hold_samples = insertion["durationFrames"] * (params.framerate // args.fps)
        final_pcm.extend(b"\x00" * hold_samples * frame_width)
        insertion["durationMs"] = insertion["durationFrames"] * 1000 / args.fps
        insertion["insertSamples"] = hold_samples
        raw_cursor_frame = boundary_frame
    final_pcm.extend(pcm[raw_cursor_frame * frame_width:])

    samples_per_video_frame = params.framerate // args.fps
    final_samples = len(final_pcm) // frame_width
    total_frames = math.ceil(final_samples / samples_per_video_frame)
    trailing_samples = total_frames * samples_per_video_frame - final_samples
    final_pcm.extend(b"\x00" * trailing_samples * frame_width)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    final_audio = args.output_dir / args.output_audio_name
    with wave.open(str(final_audio), "wb") as target:
        target.setnchannels(params.nchannels)
        target.setsampwidth(params.sampwidth)
        target.setframerate(params.framerate)
        target.writeframes(final_pcm)

    scene_timeline: list[dict[str, Any]] = []
    caption_timeline: list[dict[str, Any]] = []
    word_timeline: list[dict[str, Any]] = []
    shift_ms = 0.0
    for index, segment in enumerate(segments):
        segment_id = segment["id"]
        raw_start = raw_boundaries[index]
        raw_end = raw_boundaries[index + 1]
        timeline_start = raw_start + shift_ms
        timeline_end = raw_end + shift_ms
        span = segment_spans[segment_id]
        provider_word_keys = unique_word_keys(span["chars"])
        scene_timeline.append(
            {
                "id": segment_id,
                "kind": "narrated",
                "narration": segment["narration"],
                "rawStartMs": raw_start,
                "rawEndMs": raw_end,
                "timelineStartMs": round(timeline_start, 3),
                "timelineEndMs": round(timeline_end, 3),
                "startFrame": frame_from_ms(timeline_start, args.fps),
                "endFrame": frame_from_ms(timeline_end, args.fps),
                "providerWordKeys": provider_word_keys,
                "alignmentStatus": "provider-timestamp",
            }
        )

        segment_cards = cards_by_segment[segment_id]
        raw_card_boundaries = [raw_start]
        for previous, following in zip(segment_cards, segment_cards[1:]):
            previous_end = previous["_chars"][-1]["rawEndMs"]
            following_start = following["_chars"][0]["rawStartMs"]
            raw_card_boundaries.append(round((previous_end + following_start) / 2, 3))
        raw_card_boundaries.append(raw_end)
        segment_end_frame = frame_from_ms(timeline_end, args.fps)
        frame_cursor = frame_from_ms(timeline_start, args.fps)
        for card_index, card in enumerate(segment_cards):
            card_start_ms = raw_card_boundaries[card_index] + shift_ms
            card_end_ms = raw_card_boundaries[card_index + 1] + shift_ms
            start_frame = frame_cursor
            if start_frame >= segment_end_frame:
                raise SystemExit(
                    f"Segment {segment_id} is too short for {len(segment_cards)} caption cards"
                )
            end_frame = max(start_frame + 1, frame_from_ms(card_end_ms, args.fps))
            frame_cursor = end_frame
            result_card = {
                key: value
                for key, value in card.items()
                if key not in {"normalized", "_chars"}
            }
            result_card.update(
                {
                    "startMs": round(card_start_ms, 3),
                    "endMs": round(card_end_ms, 3),
                    "startFrame": start_frame,
                    "endFrame": end_frame,
                    "sourceWordKeys": unique_word_keys(card["_chars"]),
                    "alignmentStatus": "provider-timestamp",
                    "alignmentEvidence": "Doubao V3 sentence.words",
                }
            )
            caption_timeline.append(result_card)

        for char in span["chars"]:
            word_timeline.append(
                {
                    **char,
                    "segmentId": segment_id,
                    "timelineStartMs": round(char["rawStartMs"] + shift_ms, 3),
                    "timelineEndMs": round(char["rawEndMs"] + shift_ms, 3),
                }
            )

        for hold in hold_by_segment.get(segment_id, []):
            hold_start = raw_end + shift_ms
            hold_duration = hold["durationFrames"] * 1000 / args.fps
            boundary_evidence = hold_boundary_evidence[segment_id]
            scene_timeline.append(
                {
                    "id": str(hold.get("id") or f"hold-after-{segment_id}"),
                    "kind": "silent-hold",
                    "afterSegmentId": segment_id,
                    "timelineStartMs": round(hold_start, 3),
                    "timelineEndMs": round(hold_start + hold_duration, 3),
                    "startFrame": frame_from_ms(hold_start, args.fps),
                    "endFrame": frame_from_ms(hold_start, args.fps) + hold["durationFrames"],
                    "assets": hold.get("assets") or [],
                    "alignmentStatus": "intentional-pcm-silence",
                    "boundaryMethod": boundary_evidence["boundaryMethod"],
                    "silenceStartMs": boundary_evidence["silenceStartMs"],
                    "silenceEndMs": boundary_evidence["silenceEndMs"],
                    "guardRmsDbfs": boundary_evidence["guardRmsDbfs"],
                }
            )
            shift_ms += hold_duration

    normalize_frame_ranges(scene_timeline, caption_timeline, total_frames)

    caption_document = {
        **caption_document,
        "status": "verified-provider-timestamps",
        "fps": args.fps,
        "cards": caption_timeline,
    }
    total_duration_ms = total_frames * 1000 / args.fps
    scene_document = {
        "version": 1,
        "status": "verified-provider-timestamps",
        "fps": args.fps,
        "totalFrames": total_frames,
        "durationMs": round(total_duration_ms, 3),
        "audio": str(final_audio),
        "scenes": scene_timeline,
    }
    word_document = {
        "version": 1,
        "status": "verified-provider-timestamps",
        "source": "Doubao V3 sentence.words",
        "rawNarrationAudio": project_relative(args.audio, project, "Raw narration WAV"),
        "rawNarrationAudioSha256": sha256(args.audio),
        "ttsReport": project_relative(args.tts_report, project, "TTS report"),
        "ttsReportSha256": sha256(args.tts_report),
        "characters": word_timeline,
    }
    scene_path = args.output_dir / "scene-timeline.json"
    caption_path = args.output_dir / "caption-timeline.json"
    word_path = args.output_dir / "word-timeline.json"
    alignment_path = args.output_dir / "alignment-report.json"
    subtitle_path = args.output_dir / "subtitles.ass"
    atomic_write_json(scene_path, scene_document)
    atomic_write_json(caption_path, caption_document)
    atomic_write_json(word_path, word_document)
    alignment_report = {
        "version": 2,
        "status": "verified",
        "timestampSource": timestamp_block.get("source") or "Doubao V3 sentence.words",
        "rawNarrationAudio": project_relative(args.audio, project, "Raw narration WAV"),
        "rawNarrationAudioSha256": sha256(args.audio),
        "ttsReport": project_relative(args.tts_report, project, "TTS report"),
        "ttsReportSha256": sha256(args.tts_report),
        "wordTimeline": project_relative(word_path, project, "Word timeline"),
        "wordTimelineSha256": sha256(word_path),
        # Backward-readable aliases; new consumers use the explicit fields above.
        "sourceAudio": project_relative(args.audio, project, "Raw narration WAV"),
        "sourceAudioSha256": sha256(args.audio),
        "sourceTtsReport": project_relative(args.tts_report, project, "TTS report"),
        "sourceTtsReportSha256": sha256(args.tts_report),
        "finalAudio": project_relative(final_audio, project, "Timestamped narration WAV"),
        "finalAudioSha256": sha256(final_audio),
        "resourceId": tts_report.get("resourceId"),
        "speaker": tts_report.get("speaker"),
        "enableSubtitle": tts_report.get("enableSubtitle"),
        "requestMode": tts_report.get("requestMode"),
        "providerRequestCount": tts_report.get("providerRequestCount"),
        "providerAttemptCount": tts_report.get("providerAttemptCount"),
        "speechRate": tts_report.get("speechRate"),
        "providerLogids": tts_report.get("xTtLogids") or [],
        "providerTimestampCount": timestamp_block.get("count"),
        "alignedCharacterCount": len(timed_chars),
        "segmentCount": len(segments),
        "captionCount": len(caption_timeline),
        "holds": insertions,
        "trailingPadSamples": trailing_samples,
        "textCoverage": 1.0,
        "method": (
            "strict normalized text coverage plus Doubao provider timestamps; "
            "visual holds inserted only at verified PCM silence"
        ),
    }
    atomic_write_json(alignment_path, alignment_report)
    atomic_write_text(
        subtitle_path,
        build_ass(
            caption_timeline,
            args.fps,
            width=width,
            height=height,
            font=args.caption_font,
            font_size=args.caption_font_size,
            english_font_size=args.english_font_size,
            position_y=args.caption_position_y,
        ),
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "providerTimestamps": timestamp_block.get("count"),
                "alignedCharacters": len(timed_chars),
                "segments": len(segments),
                "captions": len(caption_timeline),
                "holds": len(insertions),
                "totalFrames": total_frames,
                "durationSeconds": round(total_frames / args.fps, 3),
                "outputDir": str(args.output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
