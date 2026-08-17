#!/usr/bin/env python3
"""Independently fail closed unless every release artifact is still valid."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

from build_editor_plan import build_editor_plan
from project_artifacts import (
    ProjectArtifactError,
    compare_render_input_inventory,
    secure_project_file,
    secure_project_path,
)
from qa_video import packet_hash, provider_timing_report, scene_starts
from validate_case import is_timezone_aware_iso8601, validate_case, validate_manifest
from validate_editable_delivery import inspect_png
from validate_editable_delivery import validate as validate_editable_delivery


SKILL_DIR = Path(__file__).resolve().parents[1]
ARTIFACT_FIELDS = (
    ("video", "videoSha256"),
    ("audioMix", "audioMixSha256"),
    ("rawNarrationAudio", "rawNarrationAudioSha256"),
    ("ttsReport", "ttsReportSha256"),
    ("wordTimeline", "wordTimelineSha256"),
    ("qaReport", "qaReportSha256"),
    ("buildReport", "buildReportSha256"),
    ("humanReview", "humanReviewSha256"),
    ("editableDelivery", "editableDeliverySha256"),
    ("editorPlan", "editorPlanSha256"),
)
FIXED_CONTACT_SHEETS = (
    "renders/qa/final-contact-sheet.png",
    "renders/qa/boundary-contact-sheet.png",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_file(project: Path, value: Any, label: str, errors: list[str]) -> Path | None:
    try:
        return secure_project_path(project, value, f"release artifact {label}")
    except ProjectArtifactError as exc:
        errors.append(str(exc))
        return None


def load_object(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"release artifact {label} is invalid JSON: {exc}")
        return {}
    if not isinstance(document, dict):
        errors.append(f"release artifact {label} JSON root must be an object")
        return {}
    return document


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def independent_media_report(
    video: Path,
    audio_mix: Path,
    build: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ffprobePassed": False,
        "decodePassed": False,
        "packetHashMatches": False,
    }
    missing_tools = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing_tools:
        errors.append("release verification tools are missing: " + ", ".join(missing_tools))
        return report

    probe_result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(video),
        ]
    )
    if probe_result.returncode != 0:
        errors.append(
            "release video ffprobe failed: "
            + (probe_result.stderr.strip() or "unknown ffprobe error")
        )
        return report
    try:
        probe = json.loads(probe_result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"release video ffprobe returned invalid JSON: {exc}")
        return report
    report["ffprobePassed"] = True
    streams = probe.get("streams") or []
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        errors.append("release video must contain exactly one video stream")
    if len(audio_streams) != 1:
        errors.append("release video must contain exactly one audio stream")
    video_stream = video_streams[0] if video_streams else {}
    audio_stream = audio_streams[0] if audio_streams else {}
    try:
        frame_rate = float(Fraction(video_stream.get("avg_frame_rate") or "0/1"))
    except (ValueError, ZeroDivisionError):
        frame_rate = 0.0
    try:
        duration = float((probe.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    report.update(
        {
            "videoCodec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": frame_rate,
            "frameCount": video_stream.get("nb_read_frames"),
            "audioCodec": audio_stream.get("codec_name"),
            "audioSampleRate": audio_stream.get("sample_rate"),
            "durationSeconds": duration,
        }
    )
    if video_stream.get("codec_name") != "h264":
        errors.append("release video codec is not H.264")
    if (video_stream.get("width"), video_stream.get("height")) != (1080, 1920):
        errors.append("release video dimensions are not 1080x1920")
    if abs(frame_rate - 30.0) > 0.01:
        errors.append("release video frame rate is not 30 fps")
    if audio_stream.get("codec_name") != "aac":
        errors.append("release audio codec is not AAC")
    if str(audio_stream.get("sample_rate") or "") != "48000":
        errors.append("release audio sample rate is not 48 kHz")
    try:
        expected_frames = int(build.get("totalFrames") or 0)
    except (TypeError, ValueError):
        expected_frames = 0
    try:
        actual_frames = int(video_stream.get("nb_read_frames") or 0)
    except (TypeError, ValueError):
        actual_frames = 0
    if expected_frames <= 0 or actual_frames != expected_frames:
        errors.append("release video frame count differs from build report")
    try:
        expected_duration = float(build.get("durationSeconds") or 0)
    except (TypeError, ValueError):
        expected_duration = 0.0
    if expected_duration <= 0 or abs(duration - expected_duration) > 0.12:
        errors.append("release video duration differs from build report")

    decode_result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ]
    )
    if decode_result.returncode != 0:
        errors.append(
            "release video full decode failed: "
            + (decode_result.stderr.strip() or "unknown decode error")
        )
    else:
        report["decodePassed"] = True
    try:
        mix_packet_hash = packet_hash(audio_mix)
        video_packet_hash = packet_hash(video)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        errors.append(f"release audio packet verification failed: {exc}")
    else:
        report["audioMixPacketHash"] = mix_packet_hash
        report["videoAudioPacketHash"] = video_packet_hash
        report["packetHashMatches"] = mix_packet_hash == video_packet_hash
        if mix_packet_hash != video_packet_hash:
            errors.append("release video audio packets differ from the approved audio mix")
    return report


def verify_contact_sheets(
    project: Path,
    video: Path,
    build: dict[str, Any],
    media: dict[str, Any],
    qa_report: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    """Re-extract the two fixed review sheets from the current video and compare."""

    report: dict[str, Any] = {"ok": False, "files": []}
    fixed: dict[str, Path] = {}
    for relative in FIXED_CONTACT_SHEETS:
        try:
            path = secure_project_file(project, relative, f"release review sheet {relative}")
            width, height = inspect_png(path)
        except (ProjectArtifactError, ValueError, OSError) as exc:
            errors.append(f"release review sheet is missing or invalid: {exc}")
            continue
        fixed[relative] = path
        report["files"].append(
            {
                "path": relative,
                "sha256": sha256(path),
                "width": width,
                "height": height,
            }
        )
    if str(qa_report.get("contactSheet") or "") != FIXED_CONTACT_SHEETS[0]:
        errors.append("release QA contactSheet must use the fixed review sheet path")
    if str(qa_report.get("boundaryContactSheet") or "") != FIXED_CONTACT_SHEETS[1]:
        errors.append("release QA boundaryContactSheet must use the fixed review sheet path")
    if len(fixed) != len(FIXED_CONTACT_SHEETS):
        return report

    try:
        duration = float(media.get("durationSeconds") or 0)
        fps = float(media.get("fps") or 0)
        starts = [
            max(0, min(duration - 0.05, value + 0.12))
            for value in scene_starts(build, fps)
        ]
    except (TypeError, ValueError, ZeroDivisionError, AttributeError) as exc:
        errors.append(f"release review-sheet timeline is malformed: {exc}")
        return report
    if duration <= 0 or fps <= 0 or not starts:
        errors.append("release review sheets require positive media timing and scene boundaries")
        return report

    with tempfile.TemporaryDirectory(prefix=".verify-contact-") as temporary:
        temporary_dir = Path(temporary)
        contact = temporary_dir / "final-contact-sheet.png"
        boundary = temporary_dir / "boundary-contact-sheet.png"
        contact_interval = max(1, duration / 12)
        contact_result = run(
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
                str(contact),
            ]
        )
        frames = [round(value * fps) for value in starts]
        rows = math.ceil(len(frames) / 4)
        select = "+".join(f"eq(n\\,{frame})" for frame in frames)
        boundary_result = run(
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
                str(boundary),
            ]
        )
        for label, result in (
            ("contact", contact_result),
            ("boundary contact", boundary_result),
        ):
            if result.returncode != 0:
                errors.append(
                    f"release independent {label} sheet extraction failed: "
                    + (result.stderr.strip() or "unknown ffmpeg error")
                )
        if contact_result.returncode != 0 or boundary_result.returncode != 0:
            return report
        try:
            inspect_png(contact)
            inspect_png(boundary)
        except (ValueError, OSError) as exc:
            errors.append(f"release independently extracted review sheet is invalid: {exc}")
            return report
        comparisons = (
            (FIXED_CONTACT_SHEETS[0], contact),
            (FIXED_CONTACT_SHEETS[1], boundary),
        )
        for relative, generated in comparisons:
            if sha256(fixed[relative]) != sha256(generated):
                errors.append(
                    f"release review sheet does not match the current video: {relative}"
                )
    report["ok"] = not any(
        "review sheet" in error or "review-sheet" in error for error in errors
    )
    return report


def verify_build_inputs(
    project: Path,
    marker: dict[str, Any],
    build: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    try:
        build_version = int(build.get("version") or 0)
    except (TypeError, ValueError):
        build_version = 0
    if build_version < 4:
        errors.append("release build report version is unsupported")
    if build.get("status") != "rendered-pending-human-review":
        errors.append("release build report status is invalid")
    for marker_path, marker_hash, build_path, build_hash in (
        ("video", "videoSha256", "video", "videoSha256"),
        ("audioMix", "audioMixSha256", "audioMix", "audioMixSha256"),
        (
            "rawNarrationAudio",
            "rawNarrationAudioSha256",
            "rawNarrationAudio",
            "rawNarrationAudioSha256",
        ),
        ("ttsReport", "ttsReportSha256", "ttsReport", "ttsReportSha256"),
        (
            "wordTimeline",
            "wordTimelineSha256",
            "wordTimeline",
            "wordTimelineSha256",
        ),
    ):
        if str(build.get(build_path) or "") != str(marker.get(marker_path) or ""):
            errors.append(f"release build report {build_path} path differs from marker")
        if str(build.get(build_hash) or "") != str(marker.get(marker_hash) or ""):
            errors.append(f"release build report {build_hash} differs from marker")
    fixed_inputs = (
        ("caseSha256", "case.json"),
        ("renderManifestSha256", "render-manifest.json"),
    )
    for hash_field, relative in fixed_inputs:
        try:
            path = secure_project_file(project, relative, f"release frozen input {relative}")
        except ProjectArtifactError as exc:
            errors.append(str(exc))
            continue
        if str(build.get(hash_field) or "") != sha256(path):
            errors.append(f"release build report {hash_field} is missing or stale")
    timed_inputs = (
        ("alignmentReport", "alignmentReportSha256"),
        ("captionTimeline", "captionTimelineSha256"),
        ("sceneTimeline", "sceneTimelineSha256"),
        ("subtitleFile", "subtitleSha256"),
        ("narrationAudio", "narrationAudioSha256"),
        ("rawNarrationAudio", "rawNarrationAudioSha256"),
        ("ttsReport", "ttsReportSha256"),
        ("wordTimeline", "wordTimelineSha256"),
    )
    for path_field, hash_field in timed_inputs:
        path = project_file(project, build.get(path_field), f"build {path_field}", errors)
        if path is None:
            continue
        if not path.is_file():
            errors.append(f"release build input is missing: {path_field}")
        elif str(build.get(hash_field) or "") != sha256(path):
            errors.append(f"release build report {hash_field} is missing or stale")

    recorded_inventory = build.get("renderInputInventory")
    current_inventory, inventory_errors = compare_render_input_inventory(
        project, recorded_inventory
    )
    errors.extend("release " + error for error in inventory_errors)
    if marker.get("renderInputInventory") != recorded_inventory:
        errors.append("release marker renderInputInventory differs from build report")
    return current_inventory or {}


def verify_human_review(
    project: Path,
    marker: dict[str, Any],
    human: dict[str, Any],
    qa_report: dict[str, Any],
    errors: list[str],
) -> None:
    if human.get("passed") is not True:
        errors.append("release human review is not passed")
    for field in ("reviewedAt", "reviewer"):
        if not str(human.get(field) or "").strip():
            errors.append(f"release human review {field} is missing")
        if str(marker.get(field) or "") != str(human.get(field) or ""):
            errors.append(f"release marker {field} differs from human review")
    if not is_timezone_aware_iso8601(human.get("reviewedAt")):
        errors.append("release human review reviewedAt must be timezone-aware ISO-8601")
    if str(human.get("reviewedArtifact") or "") != str(marker.get("video") or ""):
        errors.append("release human review identifies a different video path")
    if str(human.get("videoSha256") or "") != str(marker.get("videoSha256") or ""):
        errors.append("release human review video hash differs from marker")
    if str(human.get("editableDeliverySha256") or "") != str(
        marker.get("editableDeliverySha256") or ""
    ):
        errors.append("release human review editable hash differs from marker")
    template_path = SKILL_DIR / "assets/human-review-template.json"
    template = load_object(template_path, "human-review template", errors)
    required_checks = list((template.get("checks") or {}).keys())
    checks = human.get("checks")
    if not isinstance(checks, dict):
        errors.append("release human review checks must be an object")
        checks = {}
    for field in required_checks:
        if checks.get(field) not in (True, "passed"):
            errors.append(f"release human review check is missing or not passed: {field}")

    evidence_values = human.get("evidence")
    if not isinstance(evidence_values, list) or not evidence_values:
        errors.append("release human review evidence list is missing")
        evidence_values = []
    evidence_paths: list[str] = []
    for index, value in enumerate(evidence_values, start=1):
        path = project_file(project, value, f"human evidence {index}", errors)
        if path is None:
            continue
        relative = path.relative_to(project).as_posix()
        evidence_paths.append(relative)
        if not path.is_file():
            errors.append(f"release human evidence is missing: {relative}")
    marker_evidence = marker.get("humanEvidence")
    if not isinstance(marker_evidence, list):
        errors.append("release marker humanEvidence must bind every reviewed evidence file")
        marker_evidence = []
    bound_paths: list[str] = []
    for index, item in enumerate(marker_evidence, start=1):
        if not isinstance(item, dict):
            errors.append(f"release marker humanEvidence[{index}] must be an object")
            continue
        path = project_file(project, item.get("path"), f"humanEvidence[{index}]", errors)
        if path is None:
            continue
        relative = path.relative_to(project).as_posix()
        bound_paths.append(relative)
        if not path.is_file():
            errors.append(f"release marker human evidence is missing: {relative}")
        elif str(item.get("sha256") or "") != sha256(path):
            errors.append(f"release marker human evidence hash is stale: {relative}")
    if evidence_paths != bound_paths or len(set(bound_paths)) != len(bound_paths):
        errors.append("release marker humanEvidence differs from human review evidence")
    for required in FIXED_CONTACT_SHEETS:
        if required not in evidence_paths:
            errors.append(f"release human review must include fixed evidence: {required}")
        if required not in bound_paths:
            errors.append(f"release marker must bind fixed human evidence: {required}")
    if qa_report.get("humanEvidence") != marker_evidence:
        errors.append("release QA humanEvidence differs from release marker")
    for field, required in zip(
        ("contactSheet", "boundaryContactSheet"), FIXED_CONTACT_SHEETS
    ):
        if str(qa_report.get(field) or "") != required:
            errors.append(f"release QA {field} must use the fixed evidence path")
        elif required not in evidence_paths:
            errors.append(f"release QA {field} was not included in human review evidence")
    if qa_report.get("visualReview") != human:
        errors.append("release QA visualReview differs from the bound human review ledger")


def validate_release(project: Path) -> dict[str, Any]:
    project = project.resolve()
    marker_path = project / "renders/qa/release-ready.json"
    errors: list[str] = []
    try:
        marker_path = secure_project_file(
            project, "renders/qa/release-ready.json", "release marker"
        )
    except ProjectArtifactError as exc:
        return {"ok": False, "marker": str(marker_path), "errors": [str(exc)]}
    marker = load_object(marker_path, "release marker", errors)
    if not marker:
        return {"ok": False, "marker": str(marker_path), "errors": errors}
    if marker.get("version") != 2:
        errors.append("release marker version must be 2")
    if marker.get("contract") != "make-book-video-release-v2":
        errors.append("release marker contract is unsupported")
    if marker.get("ready") is not True:
        errors.append("release marker does not declare ready=true")

    verified: dict[str, Any] = {}
    artifact_paths: dict[str, Path] = {}
    for path_field, hash_field in ARTIFACT_FIELDS:
        path = project_file(project, marker.get(path_field), path_field, errors)
        if path is None:
            continue
        if not path.is_file():
            errors.append(f"release artifact is missing: {path.relative_to(project)}")
            continue
        artifact_paths[path_field] = path
        actual_hash = sha256(path)
        if str(marker.get(hash_field) or "") != actual_hash:
            errors.append(f"release artifact hash is stale: {hash_field}")
        verified[path_field] = {
            "path": path.relative_to(project).as_posix(),
            "sha256": actual_hash,
        }
    for field in ("editorRoute", "editorProjectId", "editorTimelineId"):
        if not str(marker.get(field) or "").strip():
            errors.append(f"release marker {field} is required")

    qa_report = (
        load_object(artifact_paths["qaReport"], "qaReport", errors)
        if "qaReport" in artifact_paths
        else {}
    )
    build = (
        load_object(artifact_paths["buildReport"], "buildReport", errors)
        if "buildReport" in artifact_paths
        else {}
    )
    human = (
        load_object(artifact_paths["humanReview"], "humanReview", errors)
        if "humanReview" in artifact_paths
        else {}
    )
    editable = (
        load_object(artifact_paths["editableDelivery"], "editableDelivery", errors)
        if "editableDelivery" in artifact_paths
        else {}
    )
    editor_plan = (
        load_object(artifact_paths["editorPlan"], "editorPlan", errors)
        if "editorPlan" in artifact_paths
        else {}
    )

    current_inventory: dict[str, Any] = {}
    if build:
        current_inventory = verify_build_inputs(project, marker, build, errors)

    release_case: dict[str, Any] = {}
    release_manifest: dict[str, Any] = {}
    try:
        release_case_path = secure_project_file(project, "case.json", "release case.json")
        release_manifest_path = secure_project_file(
            project, "render-manifest.json", "release render-manifest.json"
        )
        release_case = load_object(release_case_path, "case.json", errors)
        release_manifest = load_object(
            release_manifest_path, "render-manifest.json", errors
        )
        try:
            case_version = int(release_case.get("version") or 0)
        except (TypeError, ValueError):
            case_version = 0
        if case_version < 3:
            errors.append("release requires case.version >= 3")
        if release_case and release_manifest:
            release_contract_errors = validate_case(
                release_case,
                require_approved=True,
                project=project,
                manifest=release_manifest,
            )
            release_contract_errors.extend(
                validate_manifest(
                    project,
                    release_case,
                    release_manifest,
                    check_assets=True,
                )
            )
            errors.extend(
                "release case/manifest: " + str(error)
                for error in release_contract_errors
            )
    except (ProjectArtifactError, OSError, ValueError, TypeError, AttributeError) as exc:
        errors.append(f"release case/manifest validation failed safely: {exc}")
    media_report: dict[str, Any] = {}
    if build and "video" in artifact_paths and "audioMix" in artifact_paths:
        media_report = independent_media_report(
            artifact_paths["video"], artifact_paths["audioMix"], build, errors
        )

    independent_timing: dict[str, Any] = {}
    if build:
        try:
            independent_timing, timing_failures = provider_timing_report(project, build)
        except (SystemExit, Exception) as exc:
            errors.append(f"release provider timing verification failed: {exc}")
        else:
            if independent_timing.get("ok") is not True or timing_failures:
                errors.extend(
                    "release provider timing: " + str(error)
                    for error in timing_failures
                    or independent_timing.get("failures")
                    or ["independent provider timing verification failed"]
                )

    editable_validation: dict[str, Any] = {}
    if editable:
        if editable.get("status") != "verified":
            errors.append("release editable delivery is not verified")
        for marker_field, editable_field in (
            ("editorRoute", "route"),
            ("editorProjectId", "projectId"),
            ("editorTimelineId", "timelineId"),
        ):
            if str(marker.get(marker_field) or "") != str(editable.get(editable_field) or ""):
                errors.append(f"release {marker_field} differs from editable delivery")
        try:
            editable_validation = validate_editable_delivery(project, editable, strict=True)
        except (SystemExit, Exception) as exc:
            errors.append(f"release editable delivery validation failed: {exc}")
        else:
            if not editable_validation.get("ok"):
                errors.extend(
                    "release editable delivery: " + str(error)
                    for error in editable_validation.get("errors")
                    or ["strict validation failed"]
                )

    editor_plan_validation: dict[str, Any] = {}
    if editor_plan:
        try:
            expected_editor_plan = build_editor_plan(project)
        except (SystemExit, Exception) as exc:
            errors.append(f"release editor plan replay failed: {exc}")
        else:
            if editor_plan != expected_editor_plan:
                errors.append("release editor plan differs from deterministic replay")
            if editor_plan.get("status") != "planned-not-executed":
                errors.append("release editor plan status must be planned-not-executed")
            if editor_plan.get("editorExecutionClaimed") is not False:
                errors.append("release editor plan must not claim editor execution")
            editor_plan_validation = {
                "ok": editor_plan == expected_editor_plan,
                "status": editor_plan.get("status"),
                "editorExecutionClaimed": editor_plan.get("editorExecutionClaimed"),
            }

    if qa_report:
        if qa_report.get("ok") is not True:
            errors.append("release QA report does not declare ok=true")
        if qa_report.get("structuralOk") is not True:
            errors.append("release QA report does not declare structuralOk=true")
        if qa_report.get("decodePassed") is not True:
            errors.append("release QA report does not declare decodePassed=true")
        if qa_report.get("humanReviewPending") not in (False, None):
            errors.append("release QA report still declares human review pending")
        failures = qa_report.get("failures")
        if not isinstance(failures, list) or failures:
            errors.append("release QA report failures must be an empty array")
        qa_video_value = qa_report.get("video")
        if not isinstance(qa_video_value, dict):
            errors.append("release QA video must be an object")
            qa_video_value = {}
        if str(qa_video_value.get("sha256") or "") != str(
            marker.get("videoSha256") or ""
        ):
            errors.append("release QA report video hash differs from marker")
        qa_video = qa_video_value
        if media_report:
            expected_video_values = {
                "codec": media_report.get("videoCodec"),
                "width": media_report.get("width"),
                "height": media_report.get("height"),
            }
            for field, actual in expected_video_values.items():
                if qa_video.get(field) != actual:
                    errors.append(f"release QA video {field} differs from ffprobe")
            try:
                qa_fps = float(qa_video.get("fps") or 0)
                qa_duration = float(qa_video.get("durationSeconds") or 0)
            except (TypeError, ValueError):
                qa_fps = qa_duration = 0.0
            if abs(qa_fps - float(media_report.get("fps") or 0)) > 0.001:
                errors.append("release QA video fps differs from ffprobe")
            if abs(
                qa_duration - float(media_report.get("durationSeconds") or 0)
            ) > 0.001:
                errors.append("release QA video duration differs from ffprobe")
        qa_audio_value = qa_report.get("audio")
        if not isinstance(qa_audio_value, dict):
            errors.append("release QA audio must be an object")
            qa_audio_value = {}
        qa_audio = qa_audio_value
        if qa_audio.get("packetHashMatches") is not True:
            errors.append("release QA report does not prove the approved audio mix")
        if str(qa_audio.get("mixSha256") or "") != str(marker.get("audioMixSha256") or ""):
            errors.append("release QA report audio mix hash differs from marker")
        if str(qa_audio.get("mix") or "") != str(marker.get("audioMix") or ""):
            errors.append("release QA report audio mix path differs from marker")
        if media_report:
            if qa_audio.get("codec") != media_report.get("audioCodec"):
                errors.append("release QA audio codec differs from ffprobe")
            if str(qa_audio.get("sampleRate") or "") != str(
                media_report.get("audioSampleRate") or ""
            ):
                errors.append("release QA audio sample rate differs from ffprobe")
        qa_timing = qa_report.get("providerTiming")
        if not isinstance(qa_timing, dict) or qa_timing.get("ok") is not True:
            errors.append("release QA report providerTiming is not verified")
        elif qa_timing.get("failures") not in (None, []):
            errors.append("release QA report providerTiming still contains failures")
        if independent_timing and qa_timing != independent_timing:
            errors.append("release QA providerTiming differs from independent verification")
        qa_editable = qa_report.get("editableDelivery")
        if not isinstance(qa_editable, dict) or qa_editable.get("ok") is not True:
            errors.append("release QA report editableDelivery is not verified")
        elif editable_validation:
            for field in ("route", "projectId", "timelineId"):
                if qa_editable.get(field) != editable_validation.get(field):
                    errors.append(f"release QA editableDelivery {field} is stale")
        if build and qa_report.get("renderInputInventory") != build.get(
            "renderInputInventory"
        ):
            errors.append("release QA renderInputInventory differs from build report")
        qa_plan = qa_report.get("editorPlan")
        if not isinstance(qa_plan, dict):
            errors.append("release QA editorPlan must be an object")
        else:
            if str(qa_plan.get("path") or "") != str(marker.get("editorPlan") or ""):
                errors.append("release QA editor plan path differs from marker")
            if str(qa_plan.get("sha256") or "") != str(
                marker.get("editorPlanSha256") or ""
            ):
                errors.append("release QA editor plan hash differs from marker")
            if qa_plan.get("status") != "planned-not-executed":
                errors.append("release QA editor plan status is invalid")
            if qa_plan.get("editorExecutionClaimed") is not False:
                errors.append("release QA editor plan incorrectly claims editor execution")
    if human and qa_report:
        verify_human_review(project, marker, human, qa_report, errors)

    contact_report: dict[str, Any] = {}
    if build and qa_report and media_report and "video" in artifact_paths:
        contact_report = verify_contact_sheets(
            project,
            artifact_paths["video"],
            build,
            media_report,
            qa_report,
            errors,
        )

    return {
        "ok": not errors,
        "marker": str(marker_path),
        "markerSha256": sha256(marker_path),
        "editorRoute": marker.get("editorRoute"),
        "editorProjectId": marker.get("editorProjectId"),
        "editorTimelineId": marker.get("editorTimelineId"),
        "artifacts": verified,
        "independentMedia": media_report,
        "independentProviderTiming": independent_timing,
        "independentEditableDelivery": editable_validation,
        "independentEditorPlan": editor_plan_validation,
        "independentRenderInputInventory": current_inventory,
        "independentContactSheets": contact_report,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    try:
        report = validate_release(args.project)
    except Exception as exc:
        report = {
            "ok": False,
            "marker": str(
                args.project.resolve() / "renders/qa/release-ready.json"
            ),
            "errors": [
                "release verification failed safely on malformed evidence: "
                f"{type(exc).__name__}: {exc}"
            ],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
