#!/usr/bin/env python3
"""Verify a rendered book video and generate reproducible QA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

from build_editor_plan import build_editor_plan
from build_timestamp_timeline import validate_provider_evidence
from project_artifacts import (
    ProjectArtifactError,
    compare_render_input_inventory,
    load_json_object,
    secure_project_file,
    secure_project_path,
)
from validate_case import validate_case, validate_manifest
from validate_editable_delivery import inspect_png
from validate_editable_delivery import load_json as load_editable_json
from validate_editable_delivery import validate as validate_editable_delivery


TIMING_REPLAY_FILES = {
    "narration": "narration.timestamped.final.wav",
    "scenes": "scene-timeline.json",
    "captions": "caption-timeline.json",
    "words": "word-timeline.json",
    "alignment": "alignment-report.json",
    "subtitles": "subtitles.ass",
}


def run(command: list[str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=capture,
        text=True,
        check=True,
    )


def packet_hash(path: Path) -> str:
    result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-c",
            "copy",
            "-f",
            "md5",
            "-",
        ]
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
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
            handle.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def project_file(project: Path, value: Any, default: str) -> Path:
    try:
        return secure_project_path(
            project, value or default, "QA artifact"
        )
    except ProjectArtifactError as exc:
        raise SystemExit(str(exc)) from exc


def json_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    """Return the first deterministic JSON difference for actionable QA errors."""
    if type(expected) is not type(actual):
        return (
            f"{path} type differs: expected {type(expected).__name__}, "
            f"got {type(actual).__name__}"
        )
    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        if missing:
            return f"{path} is missing keys: {', '.join(missing)}"
        if extra:
            return f"{path} has unexpected keys: {', '.join(extra)}"
        for key in sorted(expected_keys):
            difference = json_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path} length differs: expected {len(expected)}, got {len(actual)}"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            difference = json_difference(
                expected_item, actual_item, f"{path}[{index}]"
            )
            if difference:
                return difference
        return None
    if expected != actual:
        return f"{path} differs: expected {expected!r}, got {actual!r}"
    return None


def normalized_replay_document(label: str, document: dict[str, Any]) -> dict[str, Any]:
    """Remove only temp-directory paths introduced by the replay itself."""
    normalized = dict(document)
    if label == "scenes":
        normalized["audio"] = "<timestamped-final-wav>"
    elif label == "alignment":
        normalized["wordTimeline"] = "<word-timeline>"
        normalized["finalAudio"] = "<timestamped-final-wav>"
    return normalized


def rebuild_provider_timing(
    project: Path,
    *,
    raw_audio_path: Path,
    tts_report_path: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Re-run the canonical builder from raw evidence in an isolated project dir.

    QA deliberately invokes the builder instead of deriving expectations from the
    existing alignment/timeline documents.  Only the temporary output paths are
    normalized later; audio bytes, all time values, keys, captions and ASS text
    remain exact replay evidence.
    """
    case_path = project / "case.json"
    manifest_path = project / "render-manifest.json"
    if not manifest_path.is_file():
        return None, ["deterministic provider replay requires render-manifest.json"]
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        canvas = case.get("canvas") or {}
        caption_style = manifest.get("captions") or {}
        fps = int(canvas.get("fps") or 0)
        height = int(canvas.get("height") or 0)
        if fps <= 0 or height <= 0:
            raise ValueError("case.canvas must contain positive fps and height")
        font_size = int(caption_style.get("fontSize") or 72)
        english_font_size = int(caption_style.get("englishFontSize") or 40)
        position_y = int(
            caption_style.get("positionY") or round(height * 0.78125)
        )
    except (json.JSONDecodeError, TypeError, ValueError, OSError) as exc:
        return None, [f"deterministic provider replay input is invalid: {exc}"]

    builder = Path(__file__).with_name("build_timestamp_timeline.py")
    try:
        with tempfile.TemporaryDirectory(
            prefix=".provider-timing-replay-", dir=project
        ) as temporary:
            output_dir = Path(temporary) / "timing"
            command = [
                sys.executable,
                str(builder),
                "--audio",
                str(raw_audio_path),
                "--tts-report",
                str(tts_report_path),
                "--storyboard",
                str(case_path),
                "--case",
                str(case_path),
                "--output-dir",
                str(output_dir),
                "--fps",
                str(fps),
                "--caption-font",
                str(caption_style.get("font") or "PingFang SC"),
                "--caption-font-size",
                str(font_size),
                "--english-font-size",
                str(english_font_size),
                "--caption-position-y",
                str(position_y),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                return None, [
                    "deterministic provider replay failed: "
                    + (detail or f"builder exited {completed.returncode}")
                ]
            result: dict[str, Any] = {
                "narrationBytes": (output_dir / TIMING_REPLAY_FILES["narration"]).read_bytes(),
                "subtitlesText": (output_dir / TIMING_REPLAY_FILES["subtitles"]).read_text(
                    encoding="utf-8"
                ),
            }
            for label in ("scenes", "captions", "words", "alignment"):
                result[label] = json.loads(
                    (output_dir / TIMING_REPLAY_FILES[label]).read_text(
                        encoding="utf-8"
                    )
                )
            return result, []
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"deterministic provider replay could not be read: {exc}"]


def compare_provider_replay(
    replay: dict[str, Any],
    *,
    narration_path: Path,
    scene_document: dict[str, Any],
    caption_document: dict[str, Any],
    word_document: dict[str, Any],
    alignment_document: dict[str, Any],
    subtitle_path: Path,
) -> list[str]:
    failures: list[str] = []
    actual_narration = narration_path.read_bytes()
    if replay["narrationBytes"] != actual_narration:
        failures.append(
            "timestamped narration PCM differs from deterministic raw-provider replay"
        )
    for label, actual in (
        ("scenes", scene_document),
        ("captions", caption_document),
        ("words", word_document),
        ("alignment", alignment_document),
    ):
        expected_normalized = normalized_replay_document(label, replay[label])
        actual_normalized = normalized_replay_document(label, actual)
        difference = json_difference(expected_normalized, actual_normalized)
        if difference:
            failures.append(
                f"{label} artifact differs from deterministic raw-provider replay: "
                f"{difference}"
            )
    actual_subtitles = subtitle_path.read_text(encoding="utf-8")
    if replay["subtitlesText"] != actual_subtitles:
        failures.append("ASS subtitles differ from deterministic raw-provider replay")
    return failures


def provider_timing_report(
    project: Path, build: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    project = project.resolve()
    failures: list[str] = []
    canonical_build_paths = {
        "alignmentReport": "timing/alignment-report.json",
        "captionTimeline": "timing/caption-timeline.json",
        "sceneTimeline": "timing/scene-timeline.json",
        "narrationAudio": "timing/narration.timestamped.final.wav",
        "subtitleFile": "timing/subtitles.ass",
        "rawNarrationAudio": "audio/narration.raw.wav",
        "ttsReport": "audio/narration.raw.wav.json",
        "wordTimeline": "timing/word-timeline.json",
    }
    for field, expected in canonical_build_paths.items():
        if str(build.get(field) or "") != expected:
            failures.append(f"build report {field} must use canonical path {expected}")
    alignment_path = project / canonical_build_paths["alignmentReport"]
    captions_path = project / canonical_build_paths["captionTimeline"]
    scenes_path = project / canonical_build_paths["sceneTimeline"]
    narration_path = project / canonical_build_paths["narrationAudio"]
    subtitles_path = project / canonical_build_paths["subtitleFile"]
    required = {
        "alignment report": alignment_path,
        "caption timeline": captions_path,
        "scene timeline": scenes_path,
        "timestamped narration": narration_path,
        "subtitle file": subtitles_path,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.is_file()]
    if missing:
        return {"ok": False, "missing": missing}, [
            "provider timing evidence is missing: " + "; ".join(missing)
        ]

    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    # These are canonical contract paths, not pointers supplied by copied build
    # metadata.  A forged report therefore cannot redirect QA to a substitute
    # evidence chain.
    raw_audio_path = project / "audio/narration.raw.wav"
    tts_report_path = project / "audio/narration.raw.wav.json"
    word_timeline_path = project / "timing/word-timeline.json"
    provider_required = {
        "raw provider narration": raw_audio_path,
        "provider TTS report": tts_report_path,
        "provider word timeline": word_timeline_path,
        "approved case": project / "case.json",
    }
    provider_missing = [
        f"{label}: {path}"
        for label, path in provider_required.items()
        if not path.is_file()
    ]
    if provider_missing:
        return {"ok": False, "missing": provider_missing}, [
            "provider source evidence is missing: " + "; ".join(provider_missing)
        ]

    tts_report = json.loads(tts_report_path.read_text(encoding="utf-8"))
    word_timeline = json.loads(word_timeline_path.read_text(encoding="utf-8"))
    case = json.loads((project / "case.json").read_text(encoding="utf-8"))
    captions = json.loads(captions_path.read_text(encoding="utf-8"))
    scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    cards = captions.get("cards") or []
    scene_items = scenes.get("scenes") or []
    total_frames = int(build.get("totalFrames") or scenes.get("totalFrames") or 0)

    reconciled: dict[str, Any] | None = None
    try:
        reconciled = validate_provider_evidence(tts_report, raw_audio_path, case)
    except (SystemExit, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        failures.append(f"provider source reconciliation failed: {exc}")

    replay, replay_failures = rebuild_provider_timing(
        project,
        raw_audio_path=raw_audio_path,
        tts_report_path=tts_report_path,
    )
    failures.extend(replay_failures)
    if replay is not None:
        try:
            failures.extend(
                compare_provider_replay(
                    replay,
                    narration_path=narration_path,
                    scene_document=scenes,
                    caption_document=captions,
                    word_document=word_timeline,
                    alignment_document=alignment,
                    subtitle_path=subtitles_path,
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            failures.append(f"deterministic provider replay comparison failed: {exc}")

    if alignment.get("status") != "verified":
        failures.append("provider alignment report is not verified")
    if alignment.get("requestMode") != "single":
        failures.append("narration was not generated in one provider request")
    if int(alignment.get("providerRequestCount") or 0) != 1:
        failures.append("providerRequestCount is not exactly 1")
    if int(alignment.get("providerAttemptCount") or 0) != 1:
        failures.append("providerAttemptCount is not exactly 1")
    if not alignment.get("providerLogids"):
        failures.append("provider X-Tt-Logid evidence is missing")
    if int(alignment.get("providerTimestampCount") or 0) <= 0:
        failures.append("provider timestamp count is empty")
    if alignment.get("speechRate") is None:
        failures.append("provider speech rate is not recorded")
    if build.get("speechRate") != alignment.get("speechRate"):
        failures.append("build report speech rate differs from alignment report")
    if float(alignment.get("textCoverage") or 0) != 1.0:
        failures.append("provider timestamp text coverage is not 100%")
    semantic_fields = (
        "resourceId",
        "speaker",
        "speechRate",
        "enableSubtitle",
        "requestMode",
        "providerRequestCount",
        "providerAttemptCount",
    )
    for field in semantic_fields:
        if alignment.get(field) != tts_report.get(field):
            failures.append(f"alignment {field} differs from provider TTS report")
        if build.get(field) != tts_report.get(field):
            failures.append(f"build report {field} differs from provider TTS report")
    if alignment.get("providerLogids") != tts_report.get("xTtLogids"):
        failures.append("alignment provider log IDs differ from provider TTS report")
    if build.get("providerLogids") != tts_report.get("xTtLogids"):
        failures.append("build provider log IDs differ from provider TTS report")
    provider_words = (tts_report.get("timestamps") or {}).get("words") or []
    if int(alignment.get("providerTimestampCount") or 0) != len(provider_words):
        failures.append("alignment timestamp count differs from provider TTS words")
    if captions.get("status") != "verified-provider-timestamps":
        failures.append("caption timeline is not provider-timestamp verified")
    if scenes.get("status") != "verified-provider-timestamps":
        failures.append("scene timeline is not provider-timestamp verified")
    if int(alignment.get("captionCount") or 0) != len(cards):
        failures.append("alignment caption count differs from caption timeline")
    if int(build.get("captionCount") or 0) != len(cards):
        failures.append("build caption count differs from caption timeline")
    if not scene_items:
        failures.append("scene timeline has no scenes")
    else:
        expected_start = 0
        for item in scene_items:
            start = int(item.get("startFrame") or 0)
            end = int(item.get("endFrame") or 0)
            if start != expected_start:
                failures.append(
                    f"scene {item.get('id') or 'unknown'} does not start at the previous boundary"
                )
            if end <= start:
                failures.append(f"scene {item.get('id') or 'unknown'} has no positive duration")
            expected_start = end
        if total_frames and expected_start != total_frames:
            failures.append("scene timeline does not cover the full rendered duration")

    previous_start = -1
    previous_end = -1
    provider_cards = 0
    for index, card in enumerate(cards, start=1):
        start = int(card.get("startFrame") or 0)
        end = int(card.get("endFrame") or 0)
        keys = card.get("sourceWordKeys") or []
        if card.get("alignmentStatus") == "provider-timestamp" and keys:
            provider_cards += 1
        else:
            failures.append(f"caption {index} is not backed by provider word keys")
        if start < previous_start:
            failures.append(f"caption {index} starts out of timeline order")
        if start < previous_end:
            failures.append(f"caption {index} overlaps the previous caption")
        if end <= start:
            failures.append(f"caption {index} has a non-positive duration")
        if total_frames and end > total_frames:
            failures.append(f"caption {index} exceeds the rendered timeline")
        previous_start, previous_end = start, end

    narrated_scenes = [item for item in scene_items if item.get("kind") == "narrated"]
    invalid_scenes = [
        str(item.get("id") or "unknown")
        for item in narrated_scenes
        if item.get("alignmentStatus") != "provider-timestamp"
        or not item.get("providerWordKeys")
    ]
    if invalid_scenes:
        failures.append("narrated scenes lack provider timing: " + ", ".join(invalid_scenes))
    invalid_holds = [
        str(item.get("id") or "unknown")
        for item in scene_items
        if item.get("kind") == "silent-hold"
        and item.get("alignmentStatus") != "intentional-pcm-silence"
    ]
    if invalid_holds:
        failures.append("timeline holds are not explicit PCM silence: " + ", ".join(invalid_holds))

    alignment_holds = alignment.get("holds") or []
    acoustically_safe_holds = 0
    for hold in alignment_holds:
        hold_id = str(hold.get("id") or "unknown")
        threshold_value = hold.get("silenceThresholdDbfs")
        guard_value = hold.get("guardRmsDbfs")
        threshold = float(threshold_value) if threshold_value is not None else 0.0
        guard_rms = float(guard_value) if guard_value is not None else 0.0
        duration_ms = float(hold.get("silenceDurationMs") or 0)
        minimum_ms = float(hold.get("minimumSilenceMs") or 0)
        if hold.get("boundaryMethod") != "verified-pcm-silence":
            failures.append(f"timeline hold {hold_id} lacks verified PCM silence evidence")
        elif threshold_value is None or guard_value is None or threshold >= 0:
            failures.append(f"timeline hold {hold_id} has incomplete acoustic evidence")
        elif minimum_ms <= 0 or duration_ms < minimum_ms:
            failures.append(f"timeline hold {hold_id} has an insufficient quiet interval")
        elif guard_rms > threshold:
            failures.append(f"timeline hold {hold_id} cuts through non-silent PCM")
        else:
            acoustically_safe_holds += 1
    if len(alignment_holds) != len(
        [item for item in scene_items if item.get("kind") == "silent-hold"]
    ):
        failures.append("alignment hold count differs from scene timeline")

    actual_narration_hash = sha256(narration_path)
    expected_narration_hash = str(alignment.get("finalAudioSha256") or "")
    if not expected_narration_hash or actual_narration_hash != expected_narration_hash:
        failures.append("timestamped narration hash differs from alignment report")
    if str(build.get("narrationAudioSha256") or "") != expected_narration_hash:
        failures.append("build report narration hash differs from alignment report")

    provider_artifacts = {
        "rawNarrationAudio": (raw_audio_path, "rawNarrationAudioSha256"),
        "ttsReport": (tts_report_path, "ttsReportSha256"),
        "wordTimeline": (word_timeline_path, "wordTimelineSha256"),
    }
    provider_hashes: dict[str, str] = {}
    for path_field, (artifact_path, hash_field) in provider_artifacts.items():
        relative_path = artifact_path.relative_to(project).as_posix()
        actual_hash = sha256(artifact_path)
        provider_hashes[hash_field] = actual_hash
        if str(alignment.get(path_field) or "") != relative_path:
            failures.append(f"alignment {path_field} path is missing or stale")
        if str(build.get(path_field) or "") != relative_path:
            failures.append(f"build report {path_field} path is missing or stale")
        if str(alignment.get(hash_field) or "") != actual_hash:
            failures.append(f"alignment {hash_field} is missing or stale")
        if str(build.get(hash_field) or "") != actual_hash:
            failures.append(f"build report {hash_field} is missing or stale")

    if word_timeline.get("status") != "verified-provider-timestamps":
        failures.append("word timeline is not provider-timestamp verified")
    if word_timeline.get("source") != "Doubao V3 sentence.words":
        failures.append("word timeline source is not Doubao V3 sentence.words")
    for path_field, hash_field in (
        ("rawNarrationAudio", "rawNarrationAudioSha256"),
        ("ttsReport", "ttsReportSha256"),
    ):
        if word_timeline.get(path_field) != alignment.get(path_field):
            failures.append(f"word timeline {path_field} differs from alignment")
        if word_timeline.get(hash_field) != alignment.get(hash_field):
            failures.append(f"word timeline {hash_field} differs from alignment")

    characters = word_timeline.get("characters")
    if not isinstance(characters, list):
        failures.append("word timeline characters must be a list")
        characters = []
    if reconciled is not None:
        expected_characters = reconciled["timedChars"]
        if len(characters) != len(expected_characters):
            failures.append("word timeline character count differs from provider words")
        expected_segment_ids: list[str] = []
        for segment in reconciled["segments"]:
            expected_segment_ids.extend(
                [str(segment["id"])] * len(str(segment["normalized"]))
            )
        previous_timeline_start = -1.0
        for index, (actual, expected) in enumerate(
            zip(characters, expected_characters), start=1
        ):
            if not isinstance(actual, dict):
                failures.append(f"word timeline character {index} must be an object")
                continue
            for field in (
                "key",
                "providerWordKey",
                "char",
                "rawStartMs",
                "rawEndMs",
                "confidence",
            ):
                if actual.get(field) != expected.get(field):
                    failures.append(
                        f"word timeline character {index} {field} differs from provider words"
                    )
                    break
            if index <= len(expected_segment_ids) and str(
                actual.get("segmentId") or ""
            ) != expected_segment_ids[index - 1]:
                failures.append(
                    f"word timeline character {index} has the wrong segmentId"
                )
            try:
                timeline_start = float(actual.get("timelineStartMs"))
                timeline_end = float(actual.get("timelineEndMs"))
                raw_start = float(actual.get("rawStartMs"))
                raw_end = float(actual.get("rawEndMs"))
            except (TypeError, ValueError):
                failures.append(
                    f"word timeline character {index} has invalid timeline values"
                )
                continue
            if (
                timeline_start + 0.001 < raw_start
                or timeline_end + 0.001 < raw_end
                or timeline_end < timeline_start
                or timeline_start + 0.001 < previous_timeline_start
            ):
                failures.append(
                    f"word timeline character {index} has an invalid shifted range"
                )
            previous_timeline_start = timeline_start
        if int(alignment.get("alignedCharacterCount") or 0) != len(
            expected_characters
        ):
            failures.append(
                "alignment character count differs from reconciled provider words"
            )

    manifest_hashes = {
        "alignmentReportSha256": sha256(alignment_path),
        "captionTimelineSha256": sha256(captions_path),
        "sceneTimelineSha256": sha256(scenes_path),
        "subtitleSha256": sha256(subtitles_path),
    }
    for field, actual in manifest_hashes.items():
        if str(build.get(field) or "") != actual:
            failures.append(f"build report {field} is missing or stale")
    for field, path in (
        ("caseSha256", project / "case.json"),
        ("renderManifestSha256", project / "render-manifest.json"),
    ):
        if not path.is_file():
            failures.append(f"required frozen input is missing: {path}")
        elif str(build.get(field) or "") != sha256(path):
            failures.append(f"build report {field} is missing or stale")

    dialogue_count = sum(
        1
        for line in subtitles_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("Dialogue:")
    )
    if dialogue_count != len(cards):
        failures.append("ASS dialogue count differs from caption timeline")

    replay_alignment = replay.get("alignment") if replay is not None else {}
    result = {
        "ok": not failures,
        "method": replay_alignment.get("method"),
        "timestampSource": (tts_report.get("timestamps") or {}).get("source")
        or "unspecified",
        "requestMode": tts_report.get("requestMode"),
        "providerRequestCount": tts_report.get("providerRequestCount"),
        "providerAttemptCount": tts_report.get("providerAttemptCount"),
        "providerTimestampCount": len(provider_words),
        "speechRate": tts_report.get("speechRate"),
        "alignedCharacterCount": len(reconciled["timedChars"])
        if reconciled is not None
        else 0,
        "textCoverage": 1.0 if reconciled is not None else 0.0,
        "captionCount": len(cards),
        "providerAlignedCaptionCount": provider_cards,
        "narratedSceneCount": len(narrated_scenes),
        "holdCount": len(alignment_holds),
        "acousticallySafeHoldCount": acoustically_safe_holds,
        "narrationAudioSha256": actual_narration_hash,
        "rawNarrationAudio": raw_audio_path.relative_to(project).as_posix(),
        "ttsReport": tts_report_path.relative_to(project).as_posix(),
        "wordTimeline": word_timeline_path.relative_to(project).as_posix(),
        "providerArtifactHashes": provider_hashes,
        "manifestHashes": manifest_hashes,
        "deterministicReplay": {
            "completed": replay is not None,
            "narrationPcmMatched": replay is not None
            and replay["narrationBytes"] == narration_path.read_bytes(),
            "artifactsCompared": [
                "narration PCM",
                "scene timeline",
                "caption timeline",
                "word timeline",
                "alignment report",
                "ASS subtitles",
            ],
        },
        "failures": failures,
    }
    return result, failures


def expected_duration(build: dict[str, Any]) -> float | None:
    for key in ("total_duration_s", "durationSeconds"):
        if build.get(key) is not None:
            return float(build[key])
    if build.get("durationMs") is not None:
        return float(build["durationMs"]) / 1000
    return None


def scene_starts(build: dict[str, Any], fps: float) -> list[float]:
    result: list[float] = []
    for scene in build.get("scenes") or []:
        if scene.get("start") is not None:
            result.append(float(scene["start"]))
        elif scene.get("startFrame") is not None:
            result.append(float(scene["startFrame"]) / fps)
        elif scene.get("timelineStartMs") is not None:
            result.append(float(scene["timelineStartMs"]) / 1000)
    return result


def bind_human_evidence(
    project: Path,
    human: dict[str, Any],
    *,
    required_paths: list[str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Hash reviewed files in declared order and reject ambiguous evidence."""
    failures: list[str] = []
    values = human.get("evidence")
    if not isinstance(values, list) or not values:
        return [], ["human review evidence must be a non-empty list"]
    bound: list[dict[str, str]] = []
    seen: set[str] = set()
    project = project.resolve()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str):
            failures.append(f"human review evidence {index} path must be a string")
            continue
        raw = str(value or "").strip()
        if not raw:
            failures.append(f"human review evidence {index} path is empty")
            continue
        try:
            resolved = secure_project_file(
                project, raw, f"human review evidence {index}"
            )
        except ProjectArtifactError as exc:
            failures.append(str(exc))
            continue
        canonical = resolved.relative_to(project).as_posix()
        if canonical in seen:
            failures.append(f"human review evidence is duplicated: {canonical}")
            continue
        seen.add(canonical)
        bound.append({"path": canonical, "sha256": sha256(resolved)})
    bound_paths = [item["path"] for item in bound]
    for required in required_paths:
        if required and required not in bound_paths:
            failures.append(
                f"generated QA evidence was not reviewed and bound: {required}"
            )
    return bound, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument(
        "--prepare-review",
        action="store_true",
        help="Generate structural evidence and contact sheets before human review.",
    )
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        qa_dir = secure_project_path(project, "renders/qa", "QA output directory")
        release_path = secure_project_path(
            project, "renders/qa/release-ready.json", "release marker output"
        )
    except ProjectArtifactError as exc:
        raise SystemExit(f"Unsafe QA output path: {exc}") from exc
    release_path.unlink(missing_ok=True)

    try:
        video = secure_project_file(project, "renders/video.mp4", "rendered video")
        audio_mix = secure_project_file(
            project, "renders/audio_mix.m4a", "rendered audio mix"
        )
        build_path = secure_project_file(project, "build_report.json", "build report")
        case_path = secure_project_file(project, "case.json", "case.json")
        manifest_path = secure_project_file(
            project, "render-manifest.json", "render-manifest.json"
        )
    except ProjectArtifactError as exc:
        raise SystemExit(f"Missing or unsafe required QA file: {exc}") from exc

    qa_dir.mkdir(parents=True, exist_ok=True)
    probe = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(video),
            ]
        ).stdout
    )
    (qa_dir / "final-ffprobe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(video), "-f", "null", "-"])

    volume = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if volume.returncode != 0:
        raise RuntimeError(volume.stderr)
    (qa_dir / "final-volumedetect.txt").write_text(volume.stderr, encoding="utf-8")

    build = load_json_object(build_path, "build report")
    case = load_json_object(case_path, "case.json")
    manifest = load_json_object(manifest_path, "render manifest")
    editor_plan_failures: list[str] = []
    editor_plan: dict[str, Any] = {}
    editor_plan_path = project / "editor-plan.json"
    try:
        editor_plan_path = secure_project_file(
            project, "editor-plan.json", "editor plan"
        )
        editor_plan = load_json_object(editor_plan_path, "editor plan")
        expected_editor_plan = build_editor_plan(project)
        if editor_plan != expected_editor_plan:
            editor_plan_failures.append(
                "editor plan is stale; rebuild editor-plan.json from current project inputs"
            )
        if editor_plan.get("status") != "planned-not-executed":
            editor_plan_failures.append("editor plan status must remain planned-not-executed")
        if editor_plan.get("editorExecutionClaimed") is not False:
            editor_plan_failures.append("editor plan must not claim editor execution")
    except (ProjectArtifactError, OSError, ValueError, TypeError) as exc:
        editor_plan_failures.append(f"editor plan validation failed: {exc}")
    timing, timing_failures = provider_timing_report(project, build)
    editable_path = project / "editable-delivery.json"
    editable_is_secure = False
    try:
        editable_path = secure_project_file(
            project, "editable-delivery.json", "editable delivery"
        )
    except ProjectArtifactError:
        editable_path = project / "editable-delivery.json"
    else:
        editable_is_secure = True
    if editable_is_secure:
        editable = validate_editable_delivery(
            project,
            load_editable_json(editable_path),
            strict=not args.prepare_review,
        )
    else:
        editable = {
            "ok": False,
            "route": "",
            "projectId": "",
            "timelineId": "",
            "errors": [f"missing editable delivery: {editable_path}"],
            "warnings": [],
        }
    human_path = qa_dir / "human-review.json"
    try:
        human_path = secure_project_file(
            project, "renders/qa/human-review.json", "human review"
        )
    except ProjectArtifactError:
        human = {"passed": False, "notes": "missing or unsafe human-review.json"}
        human_path = qa_dir / "human-review.json"
    else:
        human = load_json_object(human_path, "human review")
    video_sha256 = sha256(video)
    audio_mix_sha256 = sha256(audio_mix)
    editable_sha256 = sha256(editable_path) if editable_is_secure else ""
    video_stream = next((item for item in probe["streams"] if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in probe["streams"] if item.get("codec_type") == "audio"), {})
    duration = float(probe["format"]["duration"])
    frame_rate = float(Fraction(video_stream.get("avg_frame_rate") or "0/1"))

    contact_interval = max(1, duration / 12)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"fps=1/{contact_interval:.3f},scale=270:480:force_original_aspect_ratio=decrease,"
            "pad=270:480:(ow-iw)/2:(oh-ih)/2:black,tile=4x3",
            "-frames:v",
            "1",
            str(qa_dir / "final-contact-sheet.png"),
        ],
        capture=False,
    )

    starts = [max(0, min(duration - 0.05, value + 0.12)) for value in scene_starts(build, frame_rate)]
    contact_path = "renders/qa/final-contact-sheet.png"
    boundary_path = "renders/qa/boundary-contact-sheet.png"
    if starts:
        frames = [round(value * frame_rate) for value in starts]
        rows = math.ceil(len(frames) / 4)
        select = "+".join(f"eq(n\\,{frame})" for frame in frames)
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video),
                "-vf",
                f"select={select},scale=270:480:force_original_aspect_ratio=decrease,"
                f"pad=270:480:(ow-iw)/2:(oh-ih)/2:black,tile=4x{rows}:"
                f"nb_frames={len(frames)}:padding=8:margin=8:color=black",
                "-frames:v",
                "1",
                str(qa_dir / "boundary-contact-sheet.png"),
            ],
            capture=False,
        )
        (qa_dir / "boundary-times.json").write_text(
            json.dumps(starts, indent=2) + "\n", encoding="utf-8"
        )

    expected = expected_duration(build)
    audio_matches = packet_hash(audio_mix) == packet_hash(video)
    failures: list[str] = []
    human_evidence: list[dict[str, str]] = []
    failures.extend(timing_failures)
    failures.extend(editor_plan_failures)
    _, inventory_failures = compare_render_input_inventory(
        project, build.get("renderInputInventory")
    )
    failures.extend(inventory_failures)
    for evidence_label, relative in (
        ("contact sheet", contact_path),
        ("boundary contact sheet", boundary_path),
    ):
        try:
            evidence_path = secure_project_file(project, relative, evidence_label)
            inspect_png(evidence_path)
        except (ProjectArtifactError, ValueError, OSError) as exc:
            failures.append(f"{evidence_label} is missing or invalid: {exc}")
    if not starts:
        failures.append("boundary contact sheet cannot be generated without scene boundaries")
    if not args.prepare_review and not editable.get("ok"):
        failures.extend(
            "editable delivery: " + str(error)
            for error in editable.get("errors") or ["validation failed"]
        )
    if video_stream.get("codec_name") != "h264":
        failures.append("video codec is not H.264")
    if (video_stream.get("width"), video_stream.get("height")) != (1080, 1920):
        failures.append("video is not 1080x1920")
    if abs(frame_rate - 30) > 0.01:
        failures.append("video is not 30 fps")
    if audio_stream.get("codec_name") != "aac":
        failures.append("audio codec is not AAC")
    if str(audio_stream.get("sample_rate")) != "48000":
        failures.append("audio is not 48 kHz")
    if expected is None or abs(duration - expected) > 0.12:
        failures.append("duration differs from build report")
    if str(build.get("videoSha256") or "") != video_sha256:
        failures.append("rendered video hash differs from build report")
    if str(build.get("audioMixSha256") or "") != audio_mix_sha256:
        failures.append("approved audio mix hash differs from build report")
    if not audio_matches:
        failures.append("final audio packets differ from approved mix")
    if not args.prepare_review:
        try:
            case_version = int(case.get("version") or 0)
        except (TypeError, ValueError):
            case_version = 0
        if case_version < 3:
            failures.append("final release requires case.version >= 3")
        try:
            release_case_errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            release_case_errors.extend(
                validate_manifest(project, case, manifest, check_assets=True)
            )
        except Exception as exc:
            failures.append(f"release case/manifest validation failed safely: {exc}")
        else:
            failures.extend(
                "release case/manifest: " + str(error)
                for error in release_case_errors
            )
        if human.get("passed") is not True:
            failures.append("human visual review is not recorded as passed")
        if str(human.get("videoSha256") or "") != video_sha256:
            failures.append("human review is stale or does not identify the rendered video hash")
        if str(human.get("editableDeliverySha256") or "") != editable_sha256:
            failures.append(
                "human review is stale or does not identify the editable delivery hash"
            )
        if not str(human.get("reviewedAt") or "").strip():
            failures.append("human review timestamp is missing")
        if not str(human.get("reviewer") or "").strip():
            failures.append("human reviewer is missing")
        human_checks = human.get("checks") or {}
        required_human_checks = [
            "wholeFilm",
            "sceneBoundaries",
            "captionSync",
            "coverReadability",
            "coverFlashTempo",
            "visualSemantics",
            "openingSpeechContinuity",
            "narrationPace",
            "audioBalance",
            "editableTimeline",
            "editorVisualParity",
            "claimBoundary",
        ]
        try:
            visual_policy_version = int(case.get("version") or 0) >= 3
        except (TypeError, ValueError):
            visual_policy_version = False
        if visual_policy_version or "visualSourcePolicy" in case:
            required_human_checks.extend(
                ["openingSourceAndMotion", "bodySourceAndSemantics"]
            )
        for field in required_human_checks:
            if human_checks.get(field) not in (True, "passed"):
                failures.append(f"human review check is missing or not passed: {field}")
        human_evidence, evidence_failures = bind_human_evidence(
            project,
            human,
            required_paths=[
                contact_path,
                boundary_path,
            ],
        )
        failures.extend(evidence_failures)

    report = {
        "ok": not failures and not args.prepare_review,
        "structuralOk": not failures,
        "humanReviewPending": args.prepare_review,
        "failures": failures,
        "video": {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": frame_rate,
            "durationSeconds": duration,
            "sizeBytes": int(probe["format"]["size"]),
            "sha256": video_sha256,
        },
        "audio": {
            "codec": audio_stream.get("codec_name"),
            "sampleRate": audio_stream.get("sample_rate"),
            "packetHashMatches": audio_matches,
            "mix": "renders/audio_mix.m4a",
            "mixSha256": audio_mix_sha256,
        },
        "decodePassed": True,
        "providerTiming": timing,
        "editableDelivery": editable,
        "visualReview": human,
        "humanEvidence": human_evidence,
        "contactSheet": contact_path,
        "boundaryContactSheet": boundary_path,
        "renderInputInventory": build.get("renderInputInventory"),
        "editorPlan": {
            "path": "editor-plan.json",
            "sha256": sha256(editor_plan_path) if not editor_plan_failures else "",
            "status": editor_plan.get("status"),
            "editorExecutionClaimed": editor_plan.get("editorExecutionClaimed"),
        },
    }
    report_name = "qa-preflight-report.json" if args.prepare_review else "qa-report.json"
    report_path = qa_dir / report_name
    atomic_write_json(report_path, report)
    if failures:
        raise SystemExit("QA failed: " + "; ".join(failures))
    if args.prepare_review:
        print(
            f"PREPARED structural QA {video_stream['width']}x{video_stream['height']} "
            f"{frame_rate:.3f}fps {duration:.3f}s; human review is pending"
        )
        return 0
    atomic_write_json(
        release_path,
        {
            "version": 2,
            "contract": "make-book-video-release-v2",
            "ready": True,
            "video": "renders/video.mp4",
            "videoSha256": video_sha256,
            "audioMix": "renders/audio_mix.m4a",
            "audioMixSha256": audio_mix_sha256,
            "rawNarrationAudio": timing.get("rawNarrationAudio"),
            "rawNarrationAudioSha256": (
                timing.get("providerArtifactHashes") or {}
            ).get("rawNarrationAudioSha256"),
            "ttsReport": timing.get("ttsReport"),
            "ttsReportSha256": (timing.get("providerArtifactHashes") or {}).get(
                "ttsReportSha256"
            ),
            "wordTimeline": timing.get("wordTimeline"),
            "wordTimelineSha256": (
                timing.get("providerArtifactHashes") or {}
            ).get("wordTimelineSha256"),
            "qaReport": "renders/qa/qa-report.json",
            "qaReportSha256": sha256(report_path),
            "buildReport": "build_report.json",
            "buildReportSha256": sha256(build_path),
            "humanReview": "renders/qa/human-review.json",
            "humanReviewSha256": sha256(human_path),
            "humanEvidence": human_evidence,
            "editableDelivery": "editable-delivery.json",
            "editableDeliverySha256": editable_sha256,
            "renderInputInventory": build.get("renderInputInventory"),
            "editorPlan": "editor-plan.json",
            "editorPlanSha256": sha256(editor_plan_path),
            "editorRoute": editable.get("route"),
            "editorProjectId": editable.get("projectId"),
            "editorTimelineId": editable.get("timelineId"),
            "reviewedAt": human.get("reviewedAt"),
            "reviewer": human.get("reviewer"),
        },
    )
    print(
        f"PASS {video_stream['width']}x{video_stream['height']} "
        f"{frame_rate:.3f}fps {duration:.3f}s | AAC {audio_stream['sample_rate']}Hz"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
