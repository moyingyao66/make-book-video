#!/usr/bin/env python3
"""Verify a rendered book video and generate reproducible QA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from validate_editable_delivery import load_json as load_editable_json
from validate_editable_delivery import validate as validate_editable_delivery


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


def project_file(project: Path, value: Any, default: str) -> Path:
    path = Path(str(value or default))
    return path if path.is_absolute() else project / path


def provider_timing_report(
    project: Path, build: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    alignment_path = project_file(
        project, build.get("alignmentReport"), "timing/alignment-report.json"
    )
    captions_path = project_file(
        project, build.get("captionTimeline"), "timing/caption-timeline.json"
    )
    scenes_path = project_file(
        project, build.get("sceneTimeline"), "timing/scene-timeline.json"
    )
    narration_path = project_file(
        project, build.get("narrationAudio"), "timing/narration.timestamped.final.wav"
    )
    subtitles_path = project_file(
        project, build.get("subtitleFile"), "timing/subtitles.ass"
    )
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
    captions = json.loads(captions_path.read_text(encoding="utf-8"))
    scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    cards = captions.get("cards") or []
    scene_items = scenes.get("scenes") or []
    total_frames = int(build.get("totalFrames") or scenes.get("totalFrames") or 0)

    if alignment.get("status") != "verified":
        failures.append("provider alignment report is not verified")
    if alignment.get("requestMode") != "single":
        failures.append("narration was not generated in one provider request")
    if int(alignment.get("providerRequestCount") or 0) != 1:
        failures.append("providerRequestCount is not exactly 1")
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

    result = {
        "ok": not failures,
        "method": alignment.get("method"),
        "timestampSource": alignment.get("timestampSource") or "unspecified",
        "requestMode": alignment.get("requestMode"),
        "providerRequestCount": alignment.get("providerRequestCount"),
        "providerTimestampCount": alignment.get("providerTimestampCount"),
        "speechRate": alignment.get("speechRate"),
        "alignedCharacterCount": alignment.get("alignedCharacterCount"),
        "textCoverage": alignment.get("textCoverage"),
        "captionCount": len(cards),
        "providerAlignedCaptionCount": provider_cards,
        "narratedSceneCount": len(narrated_scenes),
        "holdCount": len(alignment_holds),
        "acousticallySafeHoldCount": acoustically_safe_holds,
        "narrationAudioSha256": actual_narration_hash,
        "manifestHashes": manifest_hashes,
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
    video = project / "renders/video.mp4"
    audio_mix = project / "renders/audio_mix.m4a"
    build_path = project / "build_report.json"
    missing = [str(path) for path in (video, audio_mix, build_path) if not path.is_file()]
    if missing:
        raise SystemExit("Missing required QA files: " + ", ".join(missing))

    qa_dir = project / "renders/qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    release_path = qa_dir / "release-ready.json"
    if args.prepare_review and release_path.exists():
        release_path.unlink()
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

    build = json.loads(build_path.read_text(encoding="utf-8"))
    timing, timing_failures = provider_timing_report(project, build)
    editable_path = project / "editable-delivery.json"
    if editable_path.is_file():
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
    human = (
        json.loads(human_path.read_text(encoding="utf-8"))
        if human_path.is_file()
        else {"passed": False, "notes": "missing human-review.json"}
    )
    video_sha256 = sha256(video)
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
    boundary_path: str | None = None
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
        boundary_path = "renders/qa/boundary-contact-sheet.png"

    expected = expected_duration(build)
    audio_matches = packet_hash(audio_mix) == packet_hash(video)
    failures: list[str] = []
    failures.extend(timing_failures)
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
    if not audio_matches:
        failures.append("final audio packets differ from approved mix")
    if not args.prepare_review:
        if human.get("passed") is not True:
            failures.append("human visual review is not recorded as passed")
        if str(human.get("videoSha256") or "") != video_sha256:
            failures.append("human review is stale or does not identify the rendered video hash")
        if not str(human.get("reviewedAt") or "").strip():
            failures.append("human review timestamp is missing")
        if not str(human.get("reviewer") or "").strip():
            failures.append("human reviewer is missing")
        human_checks = human.get("checks") or {}
        for field in (
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
        ):
            if human_checks.get(field) not in (True, "passed"):
                failures.append(f"human review check is missing or not passed: {field}")

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
        },
        "decodePassed": True,
        "providerTiming": timing,
        "editableDelivery": editable,
        "visualReview": human,
        "contactSheet": "renders/qa/final-contact-sheet.png",
        "boundaryContactSheet": boundary_path,
    }
    report_name = "qa-preflight-report.json" if args.prepare_review else "qa-report.json"
    (qa_dir / report_name).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("QA failed: " + "; ".join(failures))
    if args.prepare_review:
        print(
            f"PREPARED structural QA {video_stream['width']}x{video_stream['height']} "
            f"{frame_rate:.3f}fps {duration:.3f}s; human review is pending"
        )
        return 0
    release_path.write_text(
        json.dumps(
            {
                "ready": True,
                "video": "renders/video.mp4",
                "videoSha256": video_sha256,
                "qaReport": "renders/qa/qa-report.json",
                "editableDelivery": "editable-delivery.json",
                "editableDeliverySha256": sha256(editable_path),
                "editorRoute": editable.get("route"),
                "editorProjectId": editable.get("projectId"),
                "editorTimelineId": editable.get("timelineId"),
                "reviewedAt": human.get("reviewedAt"),
                "reviewer": human.get("reviewer"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"PASS {video_stream['width']}x{video_stream['height']} "
        f"{frame_rate:.3f}fps {duration:.3f}s | AAC {audio_stream['sample_rate']}Hz"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
