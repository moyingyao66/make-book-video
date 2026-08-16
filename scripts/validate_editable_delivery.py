#!/usr/bin/env python3
"""Validate that a book-video case has a real, current, editable editor project."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ALLOWED_ROUTES = {"openchatcut-local", "chatcut"}
REQUIRED_SOURCE_FILES = {
    "caseSha256": "case.json",
    "renderManifestSha256": "render-manifest.json",
    "alignmentReportSha256": "timing/alignment-report.json",
    "sceneTimelineSha256": "timing/scene-timeline.json",
    "captionTimelineSha256": "timing/caption-timeline.json",
    "narrationAudioSha256": "timing/narration.timestamped.final.wav",
}


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
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def safe_project_path(project: Path, value: Any) -> Path | None:
    raw = text(value)
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return None
    resolved = (project / path).resolve()
    try:
        resolved.relative_to(project.resolve())
    except ValueError:
        return None
    return resolved


def validate_source_hashes(
    project: Path, document: dict[str, Any], errors: list[str]
) -> dict[str, str]:
    recorded = document.get("sourceHashes") or {}
    actual: dict[str, str] = {}
    for field, relative in REQUIRED_SOURCE_FILES.items():
        path = project / relative
        if not path.is_file():
            errors.append(f"editable delivery source file is missing: {relative}")
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

    if document.get("version") != 1:
        errors.append("editable-delivery version must be 1")
    route = text(document.get("route"))
    if strict and route not in ALLOWED_ROUTES:
        errors.append("editable-delivery route must be openchatcut-local or chatcut")
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

    case_path = project / "case.json"
    manifest_path = project / "render-manifest.json"
    scenes_path = project / "timing/scene-timeline.json"
    captions_path = project / "timing/caption-timeline.json"
    if not all(path.is_file() for path in (case_path, manifest_path, scenes_path, captions_path)):
        missing = [
            str(path.relative_to(project))
            for path in (case_path, manifest_path, scenes_path, captions_path)
            if not path.is_file()
        ]
        errors.append("editable delivery cannot be checked; missing: " + ", ".join(missing))
        return {"ok": False, "errors": errors, "warnings": warnings}

    case = load_json(case_path)
    manifest = load_json(manifest_path)
    scenes_document = load_json(scenes_path)
    captions_document = load_json(captions_path)
    expected_canvas = case.get("canvas") or {}
    canvas = document.get("canvas") or {}
    for field in ("width", "height", "fps"):
        if integer(canvas.get(field)) != integer(expected_canvas.get(field)):
            errors.append(f"editable-delivery canvas.{field} differs from case.json")

    actual_hashes = validate_source_hashes(project, document, errors)

    assembly = document.get("assembly") or {}
    if assembly.get("flattenedPrimaryInput") is not False:
        errors.append("editable project cannot use a flattened primary input")
    scene_mappings = assembly.get("sceneItems") or []
    caption_mappings = assembly.get("captionItems") or []
    audio_mappings = assembly.get("audioItems") or []
    if not isinstance(scene_mappings, list):
        errors.append("assembly.sceneItems must be a list")
        scene_mappings = []
    if not isinstance(caption_mappings, list):
        errors.append("assembly.captionItems must be a list")
        caption_mappings = []
    if not isinstance(audio_mappings, list):
        errors.append("assembly.audioItems must be a list")
        audio_mappings = []

    scene_timeline = scenes_document.get("scenes") or []
    expected_scenes = {
        text(item.get("id")): item for item in scene_timeline if text(item.get("id"))
    }
    mapped_scenes: dict[str, list[dict[str, Any]]] = {}
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
        source_path = text(mapping.get("sourcePath")).replace("\\", "/").lower()
        if source_path in {"renders/video.mp4", "renders/editor-export.mp4"}:
            errors.append(f"scene item {item_id} uses a flattened final video")
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

    duplicate_scene_items = duplicate_values(scene_item_ids)
    if duplicate_scene_items:
        errors.append("editor item reused across scenes: " + ", ".join(duplicate_scene_items))

    caption_cards = captions_document.get("cards") or []
    expected_captions = {
        text(item.get("id")): item for item in caption_cards if text(item.get("id"))
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
        mapped_caption_ids.append(caption_id)
        caption_keys.append(editor_key)
    missing_captions = sorted(set(expected_captions) - set(mapped_caption_ids))
    extra_duplicates = duplicate_values(mapped_caption_ids)
    if missing_captions:
        errors.append("editable captions are missing: " + ", ".join(missing_captions))
    if extra_duplicates:
        errors.append("editable captions are duplicated: " + ", ".join(extra_duplicates))

    audio_roles: dict[str, list[dict[str, Any]]] = {}
    audio_item_ids: list[str] = []
    for index, mapping in enumerate(audio_mappings):
        if not isinstance(mapping, dict):
            errors.append(f"audioItems[{index}] must be an object")
            continue
        role = text(mapping.get("role"))
        item_id = text(mapping.get("itemId"))
        asset_id = text(mapping.get("assetId"))
        track_id = text(mapping.get("trackId"))
        if not role or not item_id or not asset_id or not track_id:
            errors.append(f"audioItems[{index}] needs role, itemId, assetId, and trackId")
            continue
        if mapping.get("editable") is not True:
            errors.append(f"audio item {item_id} is not editable")
        audio_roles.setdefault(role, []).append(mapping)
        audio_item_ids.append(item_id)
        editor_asset_ids.append(asset_id)
    narration_items = audio_roles.get("narration") or []
    if len(narration_items) != 1:
        errors.append("editable project needs exactly one narration item")
    else:
        narration_item = narration_items[0]
        total_frames = integer(scenes_document.get("totalFrames"))
        if integer(narration_item.get("startFrame")) != 0:
            errors.append("editable narration must start at frame 0")
        if integer(narration_item.get("endFrame")) != total_frames:
            errors.append("editable narration must cover the full provider timeline")
    if text((manifest.get("audio") or {}).get("bgm", {}).get("path")) and not audio_roles.get("bgm"):
        errors.append("render manifest has BGM but editable project has no BGM item")
    expected_sfx_count = len((manifest.get("audio") or {}).get("sfx") or [])
    if len(audio_roles.get("sfx") or []) != expected_sfx_count:
        errors.append("editable SFX item count differs from render manifest")

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

    readback_item_ids = {text(value) for value in readback.get("itemIds") or [] if text(value)}
    readback_asset_ids = {text(value) for value in readback.get("assetIds") or [] if text(value)}
    readback_caption_keys = {text(value) for value in readback.get("captionKeys") or [] if text(value)}
    readback_track_ids = {text(value) for value in readback.get("trackIds") or [] if text(value)}
    expected_item_ids = set(scene_item_ids + audio_item_ids)
    expected_asset_ids = set(editor_asset_ids)
    expected_caption_keys = set(caption_keys)
    expected_track_ids = {
        text(item.get("trackId"))
        for item in scene_mappings + caption_mappings + audio_mappings
        if isinstance(item, dict) and text(item.get("trackId"))
    }
    if not expected_item_ids.issubset(readback_item_ids):
        errors.append("live editor readback is missing scene or audio items")
    if not expected_asset_ids.issubset(readback_asset_ids):
        errors.append("live editor readback is missing source assets")
    if not expected_caption_keys.issubset(readback_caption_keys):
        errors.append("live editor readback is missing editable caption keys")
    if not expected_track_ids.issubset(readback_track_ids):
        errors.append("live editor readback is missing required tracks")
    if strict and (not readback_asset_ids or not readback_item_ids or not readback_track_ids):
        errors.append("live editor readback contains no assets or timeline structure")

    verification_frames = document.get("verificationFrames") or []
    if strict and (not isinstance(verification_frames, list) or len(verification_frames) < 3):
        errors.append("editable delivery needs at least three composed-frame verification records")
    elif isinstance(verification_frames, list):
        for index, frame in enumerate(verification_frames):
            if not isinstance(frame, dict) or integer(frame.get("frame")) is None or not text(frame.get("evidence")):
                errors.append(f"verificationFrames[{index}] needs frame and evidence")

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
        "captionCount": len(expected_captions),
        "mappedCaptionCount": len(set(mapped_caption_ids)),
        "audioItemCount": len(audio_item_ids),
        "readbackAssetCount": len(readback_asset_ids),
        "readbackItemCount": len(readback_item_ids),
        "readbackTrackCount": len(readback_track_ids),
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
    path = project / "editable-delivery.json"
    if not path.is_file():
        result = {"ok": False, "errors": [f"missing editable delivery: {path}"], "warnings": []}
    else:
        try:
            result = validate(project, load_json(path), strict=not args.allow_pending)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result = {"ok": False, "errors": [str(exc)], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
