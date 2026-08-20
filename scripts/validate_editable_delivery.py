#!/usr/bin/env python3
"""Validate that a book-video case has a real, current, editable editor project."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import wave
import zlib
from pathlib import Path
from typing import Any

from project_artifacts import (
    AUDIO_MAPPING_FIELDS,
    CAPTION_MAPPING_FIELDS,
    DELIVERY_AUDIO_ROLES as ALLOWED_AUDIO_ROLES,
    DELIVERY_ROUTES as ALLOWED_ROUTES,
    DELIVERY_SOURCE_FILES as REQUIRED_SOURCE_FILES,
    EDITABLE_DELIVERY_VERSION,
    OVERLAY_MAPPING_FIELDS,
    ProjectArtifactError,
    READBACK_EVIDENCE_VERSION,
    SCENE_MAPPING_FIELDS,
    secure_project_file,
    secure_project_path as checked_project_path,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def text(value: Any) -> str:
    return str(value or "").strip()


def integer(value: Any) -> int | None:
    return value if type(value) is int else None


def finite_number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def parse_finite_number_text(value: str) -> float | None:
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def exact_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def normalized_mapping(
    item: dict[str, Any], fields: tuple[str, ...]
) -> dict[str, Any]:
    return {field: item.get(field) for field in fields}


def normalized_mapping_list(
    items: Any,
    fields: tuple[str, ...],
    sort_fields: tuple[str, ...],
    label: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        errors.append(f"readback evidence {label} must be a list")
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"readback evidence {label}[{index}] must be an object")
            continue
        missing = [field for field in fields if field not in item]
        if missing:
            errors.append(
                f"readback evidence {label}[{index}] is missing fields: "
                + ", ".join(missing)
            )
        for field in (
            "manifestIndex",
            "startFrame",
            "endFrame",
            "width",
            "height",
        ):
            if field in fields and integer(item.get(field)) is None:
                errors.append(
                    f"readback evidence {label}[{index}].{field} must be a JSON integer"
                )
        for field in ("volume", "fadeInSeconds", "fadeOutSeconds"):
            if field in fields and finite_number(item.get(field)) is None:
                errors.append(
                    f"readback evidence {label}[{index}].{field} must be a finite JSON number"
                )
        normalized.append(normalized_mapping(item, fields))
    return sorted(
        normalized,
        key=lambda item: tuple(str(item.get(field)) for field in sort_fields),
    )


def normalized_id_set(
    values: Any, label: str, errors: list[str]
) -> set[str]:
    if not isinstance(values, list):
        errors.append(f"readback evidence {label} must be a list")
        return set()
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"readback evidence {label}[{index}] must be a non-empty string"
            )
            continue
        result.append(value.strip())
    duplicates = duplicate_values(result)
    if duplicates:
        errors.append(
            f"readback evidence {label} contains duplicates: "
            + ", ".join(duplicates)
        )
    return set(result)


def safe_project_path(project: Path, value: Any) -> Path | None:
    try:
        return checked_project_path(project, value, "editable delivery artifact")
    except ProjectArtifactError:
        return None


def project_relative_path(project: Path, value: Any) -> str | None:
    path = safe_project_path(project, value)
    if path is None:
        return None
    return path.relative_to(project.resolve()).as_posix()


def media_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as source:
            if source.getframerate() <= 0:
                raise ValueError(f"audio source has an invalid sample rate: {path}")
            return source.getnframes() / source.getframerate()
    except (wave.Error, EOFError):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise ValueError(
                f"cannot determine non-WAV audio duration without ffprobe: {path}"
            )
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        duration = (
            parse_finite_number_text(result.stdout.strip())
            if result.returncode == 0
            else None
        )
        if duration is None or duration <= 0:
            raise ValueError(f"cannot determine audio duration: {path}")
        return duration


def sfx_start_frame(spec: dict[str, Any], fps: int) -> int | None:
    if spec.get("startFrame") is not None:
        return integer(spec.get("startFrame"))
    seconds = finite_number(spec.get("startSeconds"))
    if seconds is None:
        return None
    # Match render_video.py, which first rounds the delay to milliseconds.
    delay_ms = round(seconds * 1000)
    return round(delay_ms * fps / 1000)


def expected_audio_items(
    project: Path,
    manifest: dict[str, Any],
    total_frames: int | None,
    fps: int | None,
    errors: list[str],
) -> dict[tuple[str, int], dict[str, Any]]:
    expected: dict[tuple[str, int], dict[str, Any]] = {}
    audio = manifest.get("audio") or {}
    if not isinstance(audio, dict):
        errors.append("render manifest audio must be an object")
        return expected
    if total_frames is None or total_frames <= 0 or fps is None or fps <= 0:
        return expected

    def source_details(value: Any, label: str) -> tuple[str, str] | None:
        relative = project_relative_path(project, value)
        if relative is None:
            errors.append(f"{label} source path is missing or outside the project")
            return None
        path = project / relative
        if not path.is_file():
            errors.append(f"{label} source does not exist: {relative}")
            return None
        return relative, sha256(path)

    narration = source_details(audio.get("narration"), "render manifest narration")
    narration_volume = finite_number(audio.get("narrationVolume") or 1.0)
    if narration_volume is None:
        errors.append("render manifest narrationVolume must be finite")
    if narration is not None and narration_volume is not None:
        expected[("narration", 0)] = {
            "sourcePath": narration[0],
            "sourceSha256": narration[1],
            "startFrame": 0,
            "endFrame": total_frames,
            "volume": narration_volume,
            "fadeInSeconds": 0.0,
            "fadeOutSeconds": 0.0,
        }

    bgm = audio.get("bgm") or {}
    if not isinstance(bgm, dict):
        errors.append("render manifest audio.bgm must be an object")
        bgm = {}
    if text(bgm.get("path")):
        bgm_source = source_details(bgm.get("path"), "render manifest BGM")
        bgm_volume = finite_number(bgm.get("volume") or 0.035)
        fade_in = finite_number(bgm.get("fadeInSeconds") or 0.0)
        fade_out = finite_number(bgm.get("fadeOutSeconds") or 0.0)
        if bgm_volume is None or fade_in is None or fade_out is None:
            errors.append("render manifest BGM volume and fades must be finite")
        elif fade_in < 0 or fade_out < 0:
            errors.append("render manifest BGM fades cannot be negative")
        elif bgm_source is not None:
            expected[("bgm", 0)] = {
                "sourcePath": bgm_source[0],
                "sourceSha256": bgm_source[1],
                "startFrame": 0,
                "endFrame": total_frames,
                "volume": bgm_volume,
                "fadeInSeconds": fade_in,
                "fadeOutSeconds": fade_out,
            }

    raw_sfx = audio.get("sfx") or []
    if not isinstance(raw_sfx, list):
        errors.append("render manifest audio.sfx must be a list")
        raw_sfx = []
    for manifest_index, raw_spec in enumerate(raw_sfx):
        if not isinstance(raw_spec, dict):
            errors.append(f"render manifest audio.sfx[{manifest_index}] must be an object")
            continue
        source = source_details(
            raw_spec.get("path"), f"render manifest SFX {manifest_index}"
        )
        start = sfx_start_frame(raw_spec, fps)
        volume = finite_number(raw_spec.get("volume") or 1.0)
        fade_in = finite_number(raw_spec.get("fadeInSeconds") or 0.0)
        fade_out = finite_number(raw_spec.get("fadeOutSeconds") or 0.0)
        if start is None or start < 0 or start >= total_frames:
            errors.append(
                f"render manifest SFX {manifest_index} needs a valid in-range startFrame or startSeconds"
            )
        if volume is None or fade_in is None or fade_out is None:
            errors.append(
                f"render manifest SFX {manifest_index} volume and fades must be finite"
            )
        elif fade_in < 0 or fade_out < 0:
            errors.append(f"render manifest SFX {manifest_index} fades cannot be negative")
        if source is None or start is None or not 0 <= start < total_frames:
            continue
        if volume is None or fade_in is None or fade_out is None:
            continue
        try:
            duration = media_duration_seconds(project / source[0])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        duration_frames = max(1, math.ceil(duration * fps - 1e-9))
        expected[("sfx", manifest_index)] = {
            "sourcePath": source[0],
            "sourceSha256": source[1],
            "startFrame": start,
            "endFrame": min(total_frames, start + duration_frames),
            "volume": volume,
            "fadeInSeconds": fade_in,
            "fadeOutSeconds": fade_out,
        }
    return expected


def inspect_png(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("invalid PNG signature")
    cursor = len(PNG_SIGNATURE)
    first = True
    width = height = 0
    channels = 0
    idat_parts: list[bytes] = []
    saw_iend = False
    while cursor < len(data):
        if len(data) - cursor < 12:
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        chunk_type = data[cursor + 4 : cursor + 8]
        chunk_end = cursor + 12 + length
        if chunk_end > len(data):
            raise ValueError("truncated PNG chunk data")
        chunk_data = data[cursor + 8 : cursor + 8 + length]
        recorded_crc = struct.unpack(">I", data[cursor + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if recorded_crc != actual_crc:
            raise ValueError(f"invalid PNG CRC for {chunk_type.decode('ascii', 'replace')}")
        if first:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("PNG first chunk must be a 13-byte IHDR")
            width, height = struct.unpack(">II", chunk_data[:8])
            if width <= 0 or height <= 0:
                raise ValueError("PNG IHDR has invalid dimensions")
            bit_depth, color_type, compression, filter_method, interlace = chunk_data[8:13]
            channel_counts = {0: 1, 2: 3, 4: 2, 6: 4}
            if bit_depth != 8 or color_type not in channel_counts:
                raise ValueError(
                    "PNG must use non-indexed 8-bit grayscale, RGB, grayscale-alpha, or RGBA"
                )
            if compression != 0 or filter_method != 0 or interlace != 0:
                raise ValueError(
                    "PNG must use standard compression/filtering and be non-interlaced"
                )
            channels = channel_counts[color_type]
            first = False
        elif chunk_type == b"IHDR":
            raise ValueError("PNG contains more than one IHDR")
        if chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        if chunk_type == b"IEND":
            if length != 0:
                raise ValueError("PNG IEND chunk must be empty")
            saw_iend = True
            cursor = chunk_end
            if cursor != len(data):
                raise ValueError("PNG has trailing bytes after IEND")
            break
        cursor = chunk_end
    if first or not idat_parts or not any(idat_parts) or not saw_iend:
        raise ValueError("PNG must contain IHDR, non-empty IDAT, and IEND chunks")
    try:
        scanlines = zlib.decompress(b"".join(idat_parts))
    except zlib.error as exc:
        raise ValueError(f"PNG IDAT is not valid zlib data: {exc}") from exc
    row_bytes = width * channels
    expected_bytes = height * (row_bytes + 1)
    if len(scanlines) != expected_bytes:
        raise ValueError(
            f"PNG decoded scanline length {len(scanlines)} differs from expected {expected_bytes}"
        )
    for row in range(height):
        filter_type = scanlines[row * (row_bytes + 1)]
        if filter_type > 4:
            raise ValueError(f"PNG scanline {row} has invalid filter type {filter_type}")
    return width, height


def manifest_scene_sources(
    project: Path,
    scene_id: str,
    spec: dict[str, Any],
    errors: list[str],
) -> dict[str, str]:
    scene_type = text(spec.get("type"))
    if scene_type in {"image", "video"}:
        raw_sources = [spec.get("path")]
    elif scene_type == "carousel":
        raw_sources = spec.get("items") or []
        if not isinstance(raw_sources, list):
            errors.append(f"render manifest scene {scene_id} carousel items must be a list")
            return {}
    elif scene_type == "solid":
        raw_sources = []
    else:
        errors.append(
            f"render manifest scene {scene_id} has unsupported type: {scene_type or '<empty>'}"
        )
        return {}

    sources: dict[str, str] = {}
    for index, value in enumerate(raw_sources):
        relative = project_relative_path(project, value)
        if relative is None:
            errors.append(
                f"render manifest scene {scene_id} source {index} is missing or outside the project"
            )
            continue
        path = project / relative
        if not path.is_file():
            errors.append(f"render manifest scene {scene_id} source is missing: {relative}")
            sources[relative] = ""
        else:
            sources[relative] = sha256(path)
    return sources


def expected_overlay_items(
    project: Path,
    scene_id: str,
    spec: dict[str, Any],
    scene: dict[str, Any],
    errors: list[str],
) -> dict[tuple[str, int], dict[str, Any]]:
    """Return the exact overlay semantics used by the reference renderer."""
    raw_overlays = spec.get("overlays") or []
    if not isinstance(raw_overlays, list):
        errors.append(f"render manifest scene {scene_id} overlays must be a list")
        return {}
    start = integer(scene.get("startFrame"))
    end = integer(scene.get("endFrame"))
    if start is None or end is None:
        return {}

    expected: dict[tuple[str, int], dict[str, Any]] = {}
    for manifest_index, raw_overlay in enumerate(raw_overlays):
        if not isinstance(raw_overlay, dict):
            errors.append(
                f"render manifest scene {scene_id} overlay {manifest_index} must be an object"
            )
            continue
        relative = project_relative_path(project, raw_overlay.get("path"))
        source_hash = ""
        if relative is None:
            errors.append(
                f"render manifest scene {scene_id} overlay {manifest_index} "
                "source path is missing or outside the project"
            )
            relative = ""
        else:
            path = project / relative
            if not path.is_file():
                errors.append(
                    f"render manifest scene {scene_id} overlay {manifest_index} "
                    f"source does not exist: {relative}"
                )
            else:
                source_hash = sha256(path)

        width = integer(raw_overlay.get("width", 0))
        height = integer(raw_overlay.get("height", 0))
        fade_in = finite_number(raw_overlay.get("fadeInSeconds") or 0.0)
        if width is None or width < 0:
            errors.append(
                f"render manifest scene {scene_id} overlay {manifest_index} "
                "width must be a non-negative JSON integer"
            )
        if height is None or height < 0:
            errors.append(
                f"render manifest scene {scene_id} overlay {manifest_index} "
                "height must be a non-negative JSON integer"
            )
        if fade_in is None or fade_in < 0:
            errors.append(
                f"render manifest scene {scene_id} overlay {manifest_index} "
                "fadeInSeconds must be a non-negative finite number"
            )
        layer_role = text(raw_overlay.get("layerRole")) or "overlay"
        expected[(scene_id, manifest_index)] = {
            "sourcePath": relative,
            "sourceSha256": source_hash,
            "startFrame": start,
            "endFrame": end,
            "layerRole": layer_role,
            # render_video.py stringifies x/y before passing them to FFmpeg.
            "x": str(raw_overlay.get("x", "(W-w)/2")),
            "y": str(raw_overlay.get("y", "(H-h)/2")),
            "width": width,
            "height": height,
            "fadeInSeconds": fade_in,
        }
    return expected


def verification_section(frame: int, total_frames: int) -> str:
    if frame * 3 < total_frames:
        return "opening"
    if frame * 3 < total_frames * 2:
        return "middle"
    return "ending"


def validate_source_hashes(
    project: Path, document: dict[str, Any], errors: list[str]
) -> dict[str, str]:
    recorded = document.get("sourceHashes") or {}
    actual: dict[str, str] = {}
    for field, relative in REQUIRED_SOURCE_FILES.items():
        try:
            path = secure_project_file(
                project, relative, f"editable delivery source {relative}"
            )
        except ProjectArtifactError as exc:
            errors.append(str(exc))
            continue
        value = sha256(path)
        actual[field] = value
        if text(recorded.get(field)) != value:
            errors.append(f"editable delivery {field} is missing or stale")
    return actual


def validate(
    project: Path, document: dict[str, Any], strict: bool = True
) -> dict[str, Any]:
    project = project.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if document.get("version") != EDITABLE_DELIVERY_VERSION:
        errors.append(
            f"editable-delivery version must be {EDITABLE_DELIVERY_VERSION}"
        )
    route = text(document.get("route"))
    if strict and route not in ALLOWED_ROUTES:
        errors.append("editable-delivery route must be chatcut")
    elif route and route not in ALLOWED_ROUTES and route != "auto":
        errors.append(f"unsupported editable-delivery route: {route}")
    if strict and document.get("status") != "verified":
        errors.append("final editable delivery requires status=verified")

    project_id = text(document.get("projectId"))
    timeline_id = text(document.get("timelineId"))
    if strict and not project_id:
        errors.append("editable-delivery projectId is required")
    if strict and not timeline_id:
        errors.append("editable-delivery timelineId is required")
    if strict and not text(document.get("editorUrl")):
        errors.append("editable-delivery editorUrl is required")

    fixed_paths: dict[str, Path] = {}
    for relative in (
        "case.json",
        "render-manifest.json",
        "timing/scene-timeline.json",
        "timing/caption-timeline.json",
    ):
        try:
            fixed_paths[relative] = secure_project_file(
                project, relative, f"editable delivery source {relative}"
            )
        except ProjectArtifactError as exc:
            errors.append(str(exc))
    if len(fixed_paths) != 4:
        return {"ok": False, "errors": errors, "warnings": warnings}

    case_path = fixed_paths["case.json"]
    manifest_path = fixed_paths["render-manifest.json"]
    scenes_path = fixed_paths["timing/scene-timeline.json"]
    captions_path = fixed_paths["timing/caption-timeline.json"]

    case = load_json(case_path)
    manifest = load_json(manifest_path)
    scenes_document = load_json(scenes_path)
    captions_document = load_json(captions_path)
    expected_canvas = case.get("canvas") or {}
    canvas = document.get("canvas") or {}
    for field in ("width", "height", "fps"):
        if integer(canvas.get(field)) != integer(expected_canvas.get(field)):
            errors.append(f"editable-delivery canvas.{field} differs from case.json")
    fps = integer(canvas.get("fps"))

    actual_hashes = validate_source_hashes(project, document, errors)

    assembly = document.get("assembly") or {}
    if assembly.get("flattenedPrimaryInput") is not False:
        errors.append("editable project cannot use a flattened primary input")
    scene_mappings = assembly.get("sceneItems") or []
    overlay_mappings = assembly.get("overlayItems")
    caption_mappings = assembly.get("captionItems") or []
    audio_mappings = assembly.get("audioItems") or []
    if not isinstance(scene_mappings, list):
        errors.append("assembly.sceneItems must be a list")
        scene_mappings = []
    if not isinstance(overlay_mappings, list):
        errors.append("assembly.overlayItems must be a list")
        overlay_mappings = []
    if not isinstance(caption_mappings, list):
        errors.append("assembly.captionItems must be a list")
        caption_mappings = []
    if not isinstance(audio_mappings, list):
        errors.append("assembly.audioItems must be a list")
        audio_mappings = []

    scene_timeline = scenes_document.get("scenes") or []
    total_frames = integer(scenes_document.get("totalFrames"))
    if not isinstance(scene_timeline, list):
        errors.append("scene timeline scenes must be a list")
        scene_timeline = []
    if total_frames is None or total_frames <= 0:
        errors.append("scene timeline totalFrames must be positive")

    expected_scenes: dict[str, dict[str, Any]] = {}
    expected_start = 0
    for index, item in enumerate(scene_timeline):
        if not isinstance(item, dict):
            errors.append(f"scene timeline item {index} must be an object")
            continue
        scene_id = text(item.get("id"))
        start = integer(item.get("startFrame"))
        end = integer(item.get("endFrame"))
        if not scene_id:
            errors.append(f"scene timeline item {index} needs an id")
            continue
        if scene_id in expected_scenes:
            errors.append(f"scene timeline has duplicate scene id: {scene_id}")
            continue
        expected_scenes[scene_id] = item
        if start is None or end is None:
            errors.append(f"scene timeline {scene_id} needs integer frame ranges")
            continue
        if start != expected_start:
            errors.append(f"scene timeline has a gap or overlap before {scene_id}")
        if end <= start:
            errors.append(f"scene timeline {scene_id} has no positive duration")
        expected_start = end
    if total_frames is not None and expected_start != total_frames:
        errors.append("scene timeline does not continuously cover totalFrames")

    scene_specs = manifest.get("sceneAssets") or {}
    if not isinstance(scene_specs, dict):
        errors.append("render manifest sceneAssets must be an object")
        scene_specs = {}
    expected_scene_sources: dict[str, dict[str, str]] = {}
    expected_overlays: dict[tuple[str, int], dict[str, Any]] = {}
    for scene_id in expected_scenes:
        spec = scene_specs.get(scene_id)
        if not isinstance(spec, dict):
            errors.append(f"render manifest is missing sceneAssets.{scene_id}")
            expected_scene_sources[scene_id] = {}
            continue
        expected_scene_sources[scene_id] = manifest_scene_sources(
            project, scene_id, spec, errors
        )
        expected_overlays.update(
            expected_overlay_items(
                project, scene_id, spec, expected_scenes[scene_id], errors
            )
        )

    mapped_scenes: dict[str, list[dict[str, Any]]] = {}
    mapped_scene_sources: dict[str, set[str]] = {}
    scene_item_ids: list[str] = []
    editor_asset_ids: list[str] = []
    for index, mapping in enumerate(scene_mappings):
        if not isinstance(mapping, dict):
            errors.append(f"sceneItems[{index}] must be an object")
            continue
        scene_id = text(mapping.get("sceneId"))
        item_id = text(mapping.get("itemId"))
        asset_id = text(mapping.get("assetId"))
        track_id = text(mapping.get("trackId"))
        if scene_id not in expected_scenes:
            errors.append(f"scene item references unknown sceneId: {scene_id or '<empty>'}")
            continue
        if not item_id or not asset_id or not track_id:
            errors.append(f"scene item for {scene_id} needs itemId, assetId, and trackId")
            continue
        if mapping.get("editable") is not True:
            errors.append(f"scene item {item_id} is not declared editable")
        raw_source_path = exact_text(mapping.get("sourcePath"))
        source_path = project_relative_path(project, raw_source_path)
        if source_path and source_path.casefold() in {
            "renders/video.mp4",
            "renders/editor-export.mp4",
        }:
            errors.append(f"scene item {item_id} uses a flattened final video")
        manifest_sources = expected_scene_sources.get(scene_id) or {}
        if manifest_sources:
            if raw_source_path is None or source_path is None:
                errors.append(
                    f"scene item {item_id} sourcePath is missing or outside the project"
                )
            elif raw_source_path != source_path or source_path not in manifest_sources:
                errors.append(
                    f"scene item {item_id} sourcePath does not match render manifest for {scene_id}"
                )
            else:
                mapped_scene_sources.setdefault(scene_id, set()).add(source_path)
                if exact_text(mapping.get("sourceSha256")) != manifest_sources[source_path]:
                    errors.append(
                        f"scene item {item_id} sourceSha256 is missing or stale"
                    )
            if source_path is not None and not (project / source_path).is_file():
                errors.append(f"scene item {item_id} sourcePath does not exist: {source_path}")
        else:
            if raw_source_path != "":
                errors.append(
                    f"scene item {item_id} sourcePath does not match source-free manifest scene {scene_id}"
                )
            if exact_text(mapping.get("sourceSha256")) != "":
                errors.append(
                    f"scene item {item_id} sourceSha256 must be empty for source-free scene {scene_id}"
                )
        scene_item_ids.append(item_id)
        editor_asset_ids.append(asset_id)
        mapped_scenes.setdefault(scene_id, []).append(mapping)

    for scene_id, expected in expected_scenes.items():
        mappings = mapped_scenes.get(scene_id) or []
        if not mappings:
            errors.append(f"editable project has no item for scene: {scene_id}")
            continue
        starts = [integer(item.get("startFrame")) for item in mappings]
        ends = [integer(item.get("endFrame")) for item in mappings]
        if any(value is None for value in starts + ends):
            errors.append(f"editable scene mappings for {scene_id} need integer frame ranges")
            continue
        expected_start = integer(expected.get("startFrame"))
        expected_end = integer(expected.get("endFrame"))
        if min(starts) != expected_start or max(ends) != expected_end:
            errors.append(f"editable scene mappings do not cover the exact range for {scene_id}")
        if any(start < expected_start or end > expected_end or end <= start for start, end in zip(starts, ends)):
            errors.append(f"editable scene item lies outside the range for {scene_id}")
        ranges = sorted(zip(starts, ends), key=lambda value: (value[0], value[1]))
        next_start = expected_start
        for start, end in ranges:
            if start != next_start:
                errors.append(
                    f"editable scene mappings for {scene_id} are not continuous"
                )
                break
            next_start = end
        if next_start != expected_end:
            errors.append(f"editable scene mappings for {scene_id} do not reach its endFrame")

        missing_sources = set(expected_scene_sources.get(scene_id, {})) - mapped_scene_sources.get(
            scene_id, set()
        )
        if missing_sources:
            errors.append(
                f"editable scene {scene_id} is missing manifest sources: "
                + ", ".join(sorted(missing_sources))
            )

    duplicate_scene_items = duplicate_values(scene_item_ids)
    if duplicate_scene_items:
        errors.append("editor item reused across scenes: " + ", ".join(duplicate_scene_items))

    mapped_overlay_keys: set[tuple[str, int]] = set()
    overlay_item_ids: list[str] = []
    for index, mapping in enumerate(overlay_mappings):
        if not isinstance(mapping, dict):
            errors.append(f"overlayItems[{index}] must be an object")
            continue
        scene_id = text(mapping.get("sceneId"))
        manifest_index = integer(mapping.get("manifestIndex"))
        item_id = text(mapping.get("itemId"))
        asset_id = text(mapping.get("assetId"))
        track_id = text(mapping.get("trackId"))
        if manifest_index is None or manifest_index < 0:
            errors.append(
                f"overlayItems[{index}] needs a non-negative manifestIndex"
            )
            continue
        if not item_id or not asset_id or not track_id:
            errors.append(
                f"overlayItems[{index}] needs itemId, assetId, and trackId"
            )
            continue
        if mapping.get("editable") is not True:
            errors.append(f"overlay item {item_id} is not editable")
        key = (scene_id, manifest_index)
        if key in mapped_overlay_keys:
            errors.append(
                f"editable overlay mapping is duplicated for {scene_id}[{manifest_index}]"
            )
        mapped_overlay_keys.add(key)
        overlay_item_ids.append(item_id)
        editor_asset_ids.append(asset_id)
        expected = expected_overlays.get(key)
        if expected is None:
            errors.append(
                "editable overlay item has no corresponding manifest entry: "
                f"{scene_id or '<empty>'}[{manifest_index}]"
            )
            continue

        raw_source_path = exact_text(mapping.get("sourcePath"))
        source_path = project_relative_path(project, raw_source_path)
        if raw_source_path != expected["sourcePath"] or source_path != expected["sourcePath"]:
            errors.append(
                f"editable overlay {scene_id}[{manifest_index}] sourcePath differs from render manifest"
            )
        elif not (project / source_path).is_file():
            errors.append(
                f"editable overlay {scene_id}[{manifest_index}] sourcePath does not exist: {source_path}"
            )
        if exact_text(mapping.get("sourceSha256")) != expected["sourceSha256"]:
            errors.append(
                f"editable overlay {scene_id}[{manifest_index}] sourceSha256 is missing or stale"
            )
        for field in ("startFrame", "endFrame", "width", "height"):
            if integer(mapping.get(field)) != expected[field]:
                errors.append(
                    f"editable overlay {scene_id}[{manifest_index}] {field} differs from render manifest"
                )
        for field in ("layerRole", "x", "y"):
            if exact_text(mapping.get(field)) != expected[field]:
                errors.append(
                    f"editable overlay {scene_id}[{manifest_index}] {field} differs from render manifest"
                )
        fade_in = finite_number(mapping.get("fadeInSeconds"))
        if fade_in is None or fade_in != expected["fadeInSeconds"]:
            errors.append(
                f"editable overlay {scene_id}[{manifest_index}] fadeInSeconds differs from render manifest"
            )

    missing_overlays = sorted(set(expected_overlays) - mapped_overlay_keys)
    if missing_overlays:
        errors.append(
            "editable overlay mappings are missing manifest entries: "
            + ", ".join(
                f"{scene_id}[{manifest_index}]"
                for scene_id, manifest_index in missing_overlays
            )
        )
    duplicate_overlay_items = duplicate_values(overlay_item_ids)
    if duplicate_overlay_items:
        errors.append(
            "editor overlay item is reused: " + ", ".join(duplicate_overlay_items)
        )

    caption_cards = captions_document.get("cards") or []
    if not isinstance(caption_cards, list):
        errors.append("caption timeline cards must be a list")
        caption_cards = []
    expected_caption_ids = [
        text(item.get("id"))
        for item in caption_cards
        if isinstance(item, dict) and text(item.get("id"))
    ]
    duplicate_expected_captions = duplicate_values(expected_caption_ids)
    if duplicate_expected_captions:
        errors.append(
            "caption timeline contains duplicate caption ids: "
            + ", ".join(duplicate_expected_captions)
        )
    expected_captions = {
        text(item.get("id")): item
        for item in caption_cards
        if isinstance(item, dict) and text(item.get("id"))
    }
    mapped_caption_ids: list[str] = []
    caption_keys: list[str] = []
    for index, mapping in enumerate(caption_mappings):
        if not isinstance(mapping, dict):
            errors.append(f"captionItems[{index}] must be an object")
            continue
        caption_id = text(mapping.get("captionId"))
        editor_key = text(mapping.get("editorKey"))
        track_id = text(mapping.get("trackId"))
        expected = expected_captions.get(caption_id)
        if expected is None:
            errors.append(f"caption item references unknown captionId: {caption_id or '<empty>'}")
            continue
        if not editor_key or not track_id:
            errors.append(f"caption item for {caption_id} needs editorKey and trackId")
            continue
        if mapping.get("editable") is not True:
            errors.append(f"caption {caption_id} is not editable")
        if integer(mapping.get("startFrame")) != integer(expected.get("startFrame")):
            errors.append(f"caption {caption_id} startFrame differs from provider timeline")
        if integer(mapping.get("endFrame")) != integer(expected.get("endFrame")):
            errors.append(f"caption {caption_id} endFrame differs from provider timeline")
        expected_zh = expected.get("zhText") if isinstance(expected.get("zhText"), str) else ""
        expected_en = expected.get("enText") if isinstance(expected.get("enText"), str) else ""
        if exact_text(mapping.get("zhText")) != expected_zh:
            errors.append(f"caption {caption_id} zhText differs from provider timeline")
        if exact_text(mapping.get("enText")) != expected_en:
            errors.append(f"caption {caption_id} enText differs from provider timeline")
        mapped_caption_ids.append(caption_id)
        caption_keys.append(editor_key)
    missing_captions = sorted(set(expected_captions) - set(mapped_caption_ids))
    extra_duplicates = duplicate_values(mapped_caption_ids)
    if missing_captions:
        errors.append("editable captions are missing: " + ", ".join(missing_captions))
    if extra_duplicates:
        errors.append("editable captions are duplicated: " + ", ".join(extra_duplicates))
    duplicate_caption_keys = duplicate_values(caption_keys)
    if duplicate_caption_keys:
        errors.append(
            "editor caption key is reused: " + ", ".join(duplicate_caption_keys)
        )

    expected_audio = expected_audio_items(
        project, manifest, total_frames, fps, errors
    )
    mapped_audio_keys: set[tuple[str, int]] = set()
    audio_item_ids: list[str] = []
    for index, mapping in enumerate(audio_mappings):
        if not isinstance(mapping, dict):
            errors.append(f"audioItems[{index}] must be an object")
            continue
        role = text(mapping.get("role"))
        manifest_index = integer(mapping.get("manifestIndex"))
        item_id = text(mapping.get("itemId"))
        asset_id = text(mapping.get("assetId"))
        track_id = text(mapping.get("trackId"))
        if role not in ALLOWED_AUDIO_ROLES:
            errors.append(
                f"audioItems[{index}] has unknown role: {role or '<empty>'}"
            )
            continue
        if manifest_index is None or manifest_index < 0:
            errors.append(f"audioItems[{index}] needs a non-negative manifestIndex")
            continue
        if not item_id or not asset_id or not track_id:
            errors.append(
                f"audioItems[{index}] needs itemId, assetId, and trackId"
            )
            continue
        if mapping.get("editable") is not True:
            errors.append(f"audio item {item_id} is not editable")
        key = (role, manifest_index)
        if key in mapped_audio_keys:
            errors.append(
                f"editable audio mapping is duplicated for {role}[{manifest_index}]"
            )
        mapped_audio_keys.add(key)
        audio_item_ids.append(item_id)
        editor_asset_ids.append(asset_id)
        expected = expected_audio.get(key)
        if expected is None:
            errors.append(
                f"editable audio item has no corresponding manifest entry: {role}[{manifest_index}]"
            )
            continue
        raw_source_path = exact_text(mapping.get("sourcePath"))
        source_path = project_relative_path(project, raw_source_path)
        if raw_source_path != expected["sourcePath"] or source_path != expected["sourcePath"]:
            errors.append(
                f"editable {role}[{manifest_index}] sourcePath differs from render manifest"
            )
        elif not (project / source_path).is_file():
            errors.append(
                f"editable {role}[{manifest_index}] sourcePath does not exist: {source_path}"
            )
        if text(mapping.get("sourceSha256")) != expected["sourceSha256"]:
            errors.append(
                f"editable {role}[{manifest_index}] sourceSha256 is missing or stale"
            )
        for field in ("startFrame", "endFrame"):
            if integer(mapping.get(field)) != expected[field]:
                errors.append(
                    f"editable {role}[{manifest_index}] {field} differs from render manifest"
                )
        for field in ("volume", "fadeInSeconds", "fadeOutSeconds"):
            value = finite_number(mapping.get(field))
            if value is None or value != expected[field]:
                errors.append(
                    f"editable {role}[{manifest_index}] {field} differs from render manifest"
                )

    missing_audio = sorted(set(expected_audio) - mapped_audio_keys)
    if missing_audio:
        errors.append(
            "editable audio mappings are missing manifest entries: "
            + ", ".join(f"{role}[{index}]" for role, index in missing_audio)
        )
    duplicate_audio_items = duplicate_values(audio_item_ids)
    if duplicate_audio_items:
        errors.append("editor audio item is reused: " + ", ".join(duplicate_audio_items))
    cross_type_item_duplicates = duplicate_values(
        scene_item_ids + overlay_item_ids + audio_item_ids
    )
    if cross_type_item_duplicates:
        errors.append(
            "editor item id is reused across scene/overlay/audio mappings: "
            + ", ".join(cross_type_item_duplicates)
        )

    readback = document.get("readback") or {}
    if strict:
        if readback.get("projectReopened") is not True:
            errors.append("editable project must be reopened before final verification")
        if not text(readback.get("source")):
            errors.append("editable project readback source is required")
        if not text(readback.get("capturedAt")):
            errors.append("editable project readback timestamp is required")
    if text(readback.get("projectId")) != project_id:
        errors.append("readback projectId differs from editable-delivery projectId")
    if text(readback.get("timelineId")) != timeline_id:
        errors.append("readback timelineId differs from editable-delivery timelineId")
    expected_item_ids = set(scene_item_ids + overlay_item_ids + audio_item_ids)
    expected_asset_ids = set(editor_asset_ids)
    expected_caption_keys = set(caption_keys)
    expected_track_ids = {
        text(item.get("trackId"))
        for item in scene_mappings + overlay_mappings + caption_mappings + audio_mappings
        if isinstance(item, dict) and text(item.get("trackId"))
    }
    readback_item_ids: set[str] = set()
    readback_asset_ids: set[str] = set()
    readback_caption_keys: set[str] = set()
    readback_track_ids: set[str] = set()
    evidence_value = readback.get("evidencePath")
    evidence_path = safe_project_path(project, evidence_value)
    evidence_hash = text(readback.get("sha256"))
    evidence_document: dict[str, Any] | None = None
    if strict or text(evidence_value) or evidence_hash:
        if evidence_path is None:
            errors.append(
                "readback evidencePath is missing, absolute, or outside the project"
            )
        elif evidence_path.suffix.lower() != ".json":
            errors.append("readback evidencePath must identify a JSON file")
        elif not evidence_path.is_file():
            errors.append("readback evidence JSON does not exist")
        else:
            actual_evidence_hash = sha256(evidence_path)
            if evidence_hash != actual_evidence_hash:
                errors.append("readback evidence SHA256 is missing or stale")
            try:
                loaded_evidence = load_json(evidence_path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"readback evidence JSON is invalid: {exc}")
            else:
                if not isinstance(loaded_evidence, dict):
                    errors.append("readback evidence JSON root must be an object")
                else:
                    evidence_document = loaded_evidence

    if evidence_document is not None:
        if evidence_document.get("version") != READBACK_EVIDENCE_VERSION:
            errors.append(
                f"readback evidence version must be {READBACK_EVIDENCE_VERSION}"
            )
        for field in ("source", "capturedAt", "projectId", "timelineId"):
            if evidence_document.get(field) != readback.get(field):
                errors.append(
                    f"readback evidence {field} differs from editable-delivery readback"
                )
        if evidence_document.get("projectReopened") is not True:
            errors.append("readback evidence must record projectReopened=true")
        if evidence_document.get("projectId") != project_id:
            errors.append("readback evidence projectId differs from editable-delivery")
        if evidence_document.get("timelineId") != timeline_id:
            errors.append("readback evidence timelineId differs from editable-delivery")
        evidence_canvas = evidence_document.get("canvas") or {}
        if not isinstance(evidence_canvas, dict):
            errors.append("readback evidence canvas must be an object")
        else:
            for field in ("width", "height", "fps"):
                if integer(evidence_canvas.get(field)) != integer(canvas.get(field)):
                    errors.append(
                        f"readback evidence canvas.{field} differs from editable-delivery"
                    )

        readback_item_ids = normalized_id_set(
            evidence_document.get("itemIds"), "itemIds", errors
        )
        readback_asset_ids = normalized_id_set(
            evidence_document.get("assetIds"), "assetIds", errors
        )
        readback_caption_keys = normalized_id_set(
            evidence_document.get("captionKeys"), "captionKeys", errors
        )
        readback_track_ids = normalized_id_set(
            evidence_document.get("trackIds"), "trackIds", errors
        )
        for actual, expected, label in (
            (readback_item_ids, expected_item_ids, "itemIds"),
            (readback_asset_ids, expected_asset_ids, "assetIds"),
            (readback_caption_keys, expected_caption_keys, "captionKeys"),
            (readback_track_ids, expected_track_ids, "trackIds"),
        ):
            if actual != expected:
                missing = sorted(expected - actual)
                extra = sorted(actual - expected)
                detail = []
                if missing:
                    detail.append("missing=" + ",".join(missing))
                if extra:
                    detail.append("extra=" + ",".join(extra))
                errors.append(
                    f"readback evidence {label} differs from mappings"
                    + (": " + "; ".join(detail) if detail else "")
                )

        expected_scene_projection = sorted(
            [normalized_mapping(item, SCENE_MAPPING_FIELDS) for item in scene_mappings],
            key=lambda item: (
                str(item.get("sceneId")),
                str(item.get("startFrame")),
                str(item.get("itemId")),
            ),
        )
        actual_scene_projection = normalized_mapping_list(
            evidence_document.get("sceneItems"),
            SCENE_MAPPING_FIELDS,
            ("sceneId", "startFrame", "itemId"),
            "sceneItems",
            errors,
        )
        if actual_scene_projection != expected_scene_projection:
            errors.append("readback evidence sceneItems differ from assembly mappings")

        expected_overlay_projection = sorted(
            [
                normalized_mapping(item, OVERLAY_MAPPING_FIELDS)
                for item in overlay_mappings
            ],
            key=lambda item: (
                str(item.get("sceneId")),
                str(item.get("manifestIndex")),
                str(item.get("itemId")),
            ),
        )
        actual_overlay_projection = normalized_mapping_list(
            evidence_document.get("overlayItems"),
            OVERLAY_MAPPING_FIELDS,
            ("sceneId", "manifestIndex", "itemId"),
            "overlayItems",
            errors,
        )
        if actual_overlay_projection != expected_overlay_projection:
            errors.append("readback evidence overlayItems differ from assembly mappings")

        expected_caption_projection = sorted(
            [
                normalized_mapping(item, CAPTION_MAPPING_FIELDS)
                for item in caption_mappings
            ],
            key=lambda item: (str(item.get("captionId")), str(item.get("editorKey"))),
        )
        actual_caption_projection = normalized_mapping_list(
            evidence_document.get("captionItems"),
            CAPTION_MAPPING_FIELDS,
            ("captionId", "editorKey"),
            "captionItems",
            errors,
        )
        if actual_caption_projection != expected_caption_projection:
            errors.append("readback evidence captionItems differ from assembly mappings")

        expected_audio_projection = sorted(
            [normalized_mapping(item, AUDIO_MAPPING_FIELDS) for item in audio_mappings],
            key=lambda item: (
                str(item.get("role")),
                str(item.get("manifestIndex")),
                str(item.get("itemId")),
            ),
        )
        actual_audio_projection = normalized_mapping_list(
            evidence_document.get("audioItems"),
            AUDIO_MAPPING_FIELDS,
            ("role", "manifestIndex", "itemId"),
            "audioItems",
            errors,
        )
        if actual_audio_projection != expected_audio_projection:
            errors.append("readback evidence audioItems differ from assembly mappings")

    if strict and (not readback_asset_ids or not readback_item_ids or not readback_track_ids):
        errors.append("live editor readback evidence contains no assets or timeline structure")

    verification_frames = document.get("verificationFrames") or []
    if strict:
        if not isinstance(verification_frames, list) or len(verification_frames) < 3:
            errors.append("editable delivery needs at least three composed-frame verification records")
        else:
            verified_frame_numbers: list[int] = []
            verified_sections: set[str] = set()
            verified_evidence_paths: list[str] = []
            for index, frame_record in enumerate(verification_frames):
                if not isinstance(frame_record, dict):
                    errors.append(f"verificationFrames[{index}] must be an object")
                    continue
                frame_number = integer(frame_record.get("frame"))
                declared_section = text(frame_record.get("position"))
                evidence_path = safe_project_path(project, frame_record.get("evidencePath"))
                evidence_hash = text(frame_record.get("sha256"))
                if frame_number is None:
                    errors.append(f"verificationFrames[{index}] needs an integer frame")
                elif total_frames is None or not 0 <= frame_number < total_frames:
                    errors.append(f"verificationFrames[{index}] frame is outside the timeline")
                else:
                    actual_section = verification_section(frame_number, total_frames)
                    verified_frame_numbers.append(frame_number)
                    verified_sections.add(actual_section)
                    if declared_section != actual_section:
                        errors.append(
                            f"verificationFrames[{index}] position must be {actual_section}"
                        )
                if evidence_path is None or not evidence_path.is_file():
                    errors.append(
                        f"verificationFrames[{index}] evidencePath is missing, outside the project, or not a file"
                    )
                else:
                    relative_evidence = evidence_path.relative_to(project).as_posix()
                    verified_evidence_paths.append(relative_evidence)
                    if evidence_path.suffix.lower() != ".png":
                        errors.append(
                            f"verificationFrames[{index}] evidence must use a .png file"
                        )
                    if evidence_hash != sha256(evidence_path):
                        errors.append(
                            f"verificationFrames[{index}] evidence SHA256 is missing or stale"
                        )
                    try:
                        png_width, png_height = inspect_png(evidence_path)
                    except (OSError, ValueError) as exc:
                        errors.append(
                            f"verificationFrames[{index}] evidence is not a valid PNG: {exc}"
                        )
                    else:
                        expected_width = integer(canvas.get("width"))
                        expected_height = integer(canvas.get("height"))
                        if (png_width, png_height) != (
                            expected_width,
                            expected_height,
                        ):
                            errors.append(
                                f"verificationFrames[{index}] PNG dimensions "
                                f"{png_width}x{png_height} differ from canvas "
                                f"{expected_width}x{expected_height}"
                            )
            if len(set(verified_frame_numbers)) < 3:
                errors.append("verificationFrames must contain at least three distinct frames")
            duplicate_evidence_paths = duplicate_values(verified_evidence_paths)
            if duplicate_evidence_paths:
                errors.append(
                    "verificationFrames must use distinct PNG evidence files: "
                    + ", ".join(duplicate_evidence_paths)
                )
            missing_sections = {"opening", "middle", "ending"} - verified_sections
            if missing_sections:
                errors.append(
                    "verificationFrames must cover opening, middle, and ending; missing: "
                    + ", ".join(sorted(missing_sections))
                )

    optional_export = document.get("optionalEditorExport") or {}
    export_path = safe_project_path(project, optional_export.get("path"))
    if text(optional_export.get("path")):
        if export_path is None or not export_path.is_file():
            errors.append("optional editor export path is invalid or missing")
        elif text(optional_export.get("sha256")) != sha256(export_path):
            errors.append("optional editor export hash is missing or stale")

    result = {
        "ok": not errors,
        "route": route,
        "projectId": project_id,
        "timelineId": timeline_id,
        "sceneCount": len(expected_scenes),
        "mappedSceneCount": len(mapped_scenes),
        "overlayCount": len(expected_overlays),
        "mappedOverlayCount": len(mapped_overlay_keys),
        "captionCount": len(expected_captions),
        "mappedCaptionCount": len(set(mapped_caption_ids)),
        "audioItemCount": len(audio_item_ids),
        "readbackAssetCount": len(readback_asset_ids),
        "readbackItemCount": len(readback_item_ids),
        "readbackTrackCount": len(readback_track_ids),
        "verificationFrameCount": len(verification_frames)
        if isinstance(verification_frames, list)
        else 0,
        "sourceHashes": actual_hashes,
        "errors": errors,
        "warnings": warnings,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        path = secure_project_file(
            project, "editable-delivery.json", "editable-delivery.json"
        )
    except ProjectArtifactError as exc:
        result = {"ok": False, "errors": [str(exc)], "warnings": []}
    else:
        try:
            result = validate(project, load_json(path), strict=not args.allow_pending)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result = {"ok": False, "errors": [str(exc)], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
