#!/usr/bin/env python3
"""Build an adapter-neutral, deterministic editor assembly plan.

This script does not call an editor and never records editor work as completed.  It
freezes the exact source files, frame ranges, effective manifest parameters, and
ordered operations that an editor-specific adapter must later execute and read
back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any


PLAN_VERSION = 1
PLAN_CONTRACT = "make-book-video-editor-plan-v1"
ALLOWED_SCENE_TYPES = {"image", "video", "carousel", "solid"}
ALLOWED_FIT_MODES = {"cover", "contain", "stretch"}
GENERATED_MEDIA_ROOTS = {"renders", "output"}


class PlanError(ValueError):
    """Raised when an input cannot produce an exact editor plan."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PlanError(f"{label} is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"{label} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PlanError(f"{label} must be a JSON object: {path}")
    return document


def json_integer(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise PlanError(f"{label} must be a JSON integer")
    if minimum is not None and value < minimum:
        raise PlanError(f"{label} must be at least {minimum}")
    return value


def finite_number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if type(value) not in (int, float):
        raise PlanError(f"{label} must be a finite JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise PlanError(f"{label} must be a finite JSON number")
    if minimum is not None and result < minimum:
        raise PlanError(f"{label} must be at least {minimum}")
    return result


def optional_number(
    document: dict[str, Any], key: str, default: float, label: str, minimum: float = 0.0
) -> float:
    value = document[key] if key in document and document[key] is not None else default
    return finite_number(value, f"{label}.{key}", minimum=minimum)


def renderer_number(
    document: dict[str, Any], key: str, default: float, label: str, minimum: float = 0.0
) -> float:
    """Mirror render_video.py's ``value or default`` numeric semantics."""
    value = document.get(key)
    if value is None or value == 0:
        value = default
    return finite_number(value, f"{label}.{key}", minimum=minimum)


def optional_integer(
    document: dict[str, Any], key: str, default: int, label: str, minimum: int = 0
) -> int:
    value = document[key] if key in document and document[key] is not None else default
    return json_integer(value, f"{label}.{key}", minimum=minimum)


def renderer_integer(
    document: dict[str, Any], key: str, default: int, label: str, minimum: int = 0
) -> int:
    """Mirror render_video.py/build_video.py's ``value or default`` integers."""
    value = document.get(key)
    if value is None or value == 0:
        value = default
    return json_integer(value, f"{label}.{key}", minimum=minimum)


def exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise PlanError(f"{label} must be a JSON boolean")
    return value


def relative_file(
    project: Path,
    value: Any,
    label: str,
    *,
    reject_generated_media: bool = False,
) -> tuple[str, Path, str]:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{label} must be a non-empty project-relative path")
    raw = value.strip()
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise PlanError(f"{label} escapes the project: {raw}")
    resolved_project = project.resolve()
    resolved = (resolved_project / path).resolve()
    try:
        relative = resolved.relative_to(resolved_project).as_posix()
    except ValueError as exc:
        raise PlanError(f"{label} escapes the project: {raw}") from exc
    relative_parts = Path(relative).parts
    if reject_generated_media and relative_parts and relative_parts[0] in GENERATED_MEDIA_ROOTS:
        raise PlanError(
            f"{label} points at generated/flattened media instead of an original source: {relative}"
        )
    if not resolved.is_file():
        raise PlanError(f"{label} does not exist: {relative}")
    digest = sha256(resolved)
    if reject_generated_media:
        flattened = project / "renders/video.mp4"
        if flattened.is_file() and resolved != flattened.resolve() and digest == sha256(flattened):
            raise PlanError(
                f"{label} duplicates renders/video.mp4; flattened MP4 input is forbidden"
            )
    return relative, resolved, digest


def project_output_path(project: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PlanError("--output must be a non-empty project-relative path")
    raw = Path(value.strip())
    if raw.is_absolute() or ".." in raw.parts:
        raise PlanError("--output must stay inside the project")
    resolved_project = project.resolve()
    output = (resolved_project / raw).resolve()
    try:
        output.relative_to(resolved_project)
    except ValueError as exc:
        raise PlanError("--output must stay inside the project") from exc
    return output


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                document,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def require_canvas(document: dict[str, Any], label: str) -> dict[str, int]:
    canvas = document.get("canvas")
    if not isinstance(canvas, dict):
        raise PlanError(f"{label}.canvas must be an object")
    return {
        "width": json_integer(canvas.get("width"), f"{label}.canvas.width", minimum=1),
        "height": json_integer(canvas.get("height"), f"{label}.canvas.height", minimum=1),
        "fps": json_integer(canvas.get("fps"), f"{label}.canvas.fps", minimum=1),
    }


def require_unique_id(item: dict[str, Any], label: str, seen: set[str]) -> str:
    value = item.get("id")
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{label}.id must be a non-empty string")
    identifier = value.strip()
    if identifier in seen:
        raise PlanError(f"{label}.id is duplicated: {identifier}")
    seen.add(identifier)
    return identifier


def ordered_scenes(
    scene_document: dict[str, Any], fps: int
) -> tuple[list[dict[str, Any]], int]:
    if scene_document.get("status") != "verified-provider-timestamps":
        raise PlanError("scene timeline is not verified-provider-timestamps")
    if json_integer(scene_document.get("fps"), "scene timeline fps", minimum=1) != fps:
        raise PlanError("scene timeline fps differs from the project canvas")
    total_frames = json_integer(
        scene_document.get("totalFrames"), "scene timeline totalFrames", minimum=1
    )
    raw_scenes = scene_document.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise PlanError("scene timeline scenes must be a non-empty list")
    seen: set[str] = set()
    scenes: list[dict[str, Any]] = []
    for source_index, raw in enumerate(raw_scenes):
        if not isinstance(raw, dict):
            raise PlanError(f"scene timeline scenes[{source_index}] must be an object")
        identifier = require_unique_id(raw, f"scene timeline scenes[{source_index}]", seen)
        start = json_integer(raw.get("startFrame"), f"scene {identifier}.startFrame", minimum=0)
        end = json_integer(raw.get("endFrame"), f"scene {identifier}.endFrame", minimum=1)
        if not start < end <= total_frames:
            raise PlanError(
                f"scene {identifier} frame range [{start}, {end}) is outside [0, {total_frames})"
            )
        scenes.append({**raw, "id": identifier, "startFrame": start, "endFrame": end})
    scenes.sort(key=lambda item: (item["startFrame"], item["endFrame"], item["id"]))
    cursor = 0
    for scene in scenes:
        if scene["startFrame"] != cursor:
            raise PlanError(
                f"scene timeline has a gap or overlap before {scene['id']}: "
                f"expected {cursor}, got {scene['startFrame']}"
            )
        cursor = scene["endFrame"]
    if cursor != total_frames:
        raise PlanError(
            f"scene timeline ends at frame {cursor}, not totalFrames {total_frames}"
        )
    return scenes, total_frames


def case_scene_ids(case: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, Any]]]:
    result: set[str] = set()
    caption_by_id: dict[str, dict[str, Any]] = {}
    segment_ids: set[str] = set()
    segments = case.get("segments")
    if not isinstance(segments, list) or not segments:
        raise PlanError("case.segments must be a non-empty list")
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise PlanError(f"case.segments[{index}] must be an object")
        segment_id = require_unique_id(segment, f"case.segments[{index}]", segment_ids)
        result.add(segment_id)
        captions = segment.get("captions")
        if not isinstance(captions, list) or not captions:
            raise PlanError(f"case segment {segment_id} must have caption cards")
        for caption_index, caption in enumerate(captions):
            if not isinstance(caption, dict):
                raise PlanError(
                    f"case segment {segment_id} caption {caption_index} must be an object"
                )
            caption_id = caption.get("id")
            if not isinstance(caption_id, str) or not caption_id.strip():
                raise PlanError(
                    f"case segment {segment_id} caption {caption_index} needs an id"
                )
            caption_id = caption_id.strip()
            if caption_id in caption_by_id:
                raise PlanError(f"case caption id is duplicated: {caption_id}")
            for field in ("zhText", "enText"):
                if not isinstance(caption.get(field), str):
                    raise PlanError(f"case caption {caption_id}.{field} must be a string")
            caption_by_id[caption_id] = {
                "segmentId": segment_id,
                "zhText": caption["zhText"],
                "enText": caption["enText"],
            }
    hold_ids: set[str] = set()
    holds = case.get("timelineHolds") or []
    if not isinstance(holds, list):
        raise PlanError("case.timelineHolds must be a list")
    for index, hold in enumerate(holds):
        if not isinstance(hold, dict):
            raise PlanError(f"case.timelineHolds[{index}] must be an object")
        result.add(require_unique_id(hold, f"case.timelineHolds[{index}]", hold_ids))
    if segment_ids & hold_ids:
        duplicate = sorted(segment_ids & hold_ids)[0]
        raise PlanError(f"case segment and hold ids overlap: {duplicate}")
    return result, caption_by_id


def caption_style(manifest: dict[str, Any], canvas: dict[str, int]) -> dict[str, Any]:
    raw = manifest.get("captions")
    if not isinstance(raw, dict):
        raise PlanError("render manifest captions must be an object")
    mode = raw.get("mode")
    if mode not in {"bilingual", "zh-only"}:
        raise PlanError("render manifest captions.mode must be bilingual or zh-only")
    require_english = exact_bool(
        raw.get("requireEnglish", mode == "bilingual"),
        "render manifest captions.requireEnglish",
    )
    if mode == "bilingual" and not require_english:
        raise PlanError("bilingual captions require requireEnglish=true")
    font = raw.get("font", "PingFang SC")
    if not isinstance(font, str) or not font.strip():
        raise PlanError("render manifest captions.font must be a non-empty string")
    font_size = renderer_integer(raw, "fontSize", 72, "render manifest captions", 1)
    english_size = renderer_integer(
        raw, "englishFontSize", 40, "render manifest captions", 1
    )
    position_y = renderer_integer(
        raw,
        "positionY",
        round(canvas["height"] * 0.78125),
        "render manifest captions",
        0,
    )
    safe_bottom = optional_integer(
        raw, "safeBottomPx", 360, "render manifest captions", 0
    )
    if position_y > canvas["height"] - safe_bottom:
        raise PlanError("caption positionY intrudes into the declared bottom safe area")
    burn_in = exact_bool(raw.get("burnIn", True), "render manifest captions.burnIn")
    return {
        "mode": mode,
        "requireEnglish": require_english,
        "font": font.strip(),
        "fontSize": font_size,
        "englishFontSize": english_size,
        "positionY": position_y,
        "safeBottomPx": safe_bottom,
        "referenceBurnIn": burn_in,
    }


def ordered_captions(
    caption_document: dict[str, Any],
    case_captions: dict[str, dict[str, Any]],
    scenes_by_id: dict[str, dict[str, Any]],
    fps: int,
    total_frames: int,
    style: dict[str, Any],
) -> list[dict[str, Any]]:
    if caption_document.get("status") != "verified-provider-timestamps":
        raise PlanError("caption timeline is not verified-provider-timestamps")
    if json_integer(caption_document.get("fps"), "caption timeline fps", minimum=1) != fps:
        raise PlanError("caption timeline fps differs from the project canvas")
    cards = caption_document.get("cards")
    if not isinstance(cards, list) or not cards:
        raise PlanError("caption timeline cards must be a non-empty list")
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for source_index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise PlanError(f"caption timeline cards[{source_index}] must be an object")
        caption_id = require_unique_id(card, f"caption timeline cards[{source_index}]", seen)
        expected = case_captions.get(caption_id)
        if expected is None:
            raise PlanError(f"caption timeline contains unknown case caption: {caption_id}")
        segment_id = card.get("segmentId")
        if segment_id != expected["segmentId"] or segment_id not in scenes_by_id:
            raise PlanError(f"caption {caption_id} has an invalid segmentId")
        for field in ("zhText", "enText"):
            if not isinstance(card.get(field), str) or card[field] != expected[field]:
                raise PlanError(f"caption {caption_id}.{field} differs from case.json")
        if style["mode"] == "bilingual" and not card["enText"].strip():
            raise PlanError(f"bilingual caption {caption_id} has empty enText")
        start = json_integer(card.get("startFrame"), f"caption {caption_id}.startFrame", minimum=0)
        end = json_integer(card.get("endFrame"), f"caption {caption_id}.endFrame", minimum=1)
        scene = scenes_by_id[segment_id]
        if not scene["startFrame"] <= start < end <= scene["endFrame"]:
            raise PlanError(
                f"caption {caption_id} range [{start}, {end}) is outside scene {segment_id}"
            )
        if end > total_frames:
            raise PlanError(f"caption {caption_id} ends after totalFrames")
        result.append(
            {
                "planId": "",
                "order": 0,
                "captionId": caption_id,
                "segmentId": segment_id,
                "trackRole": "captions",
                "startFrame": start,
                "endFrame": end,
                "zhText": card["zhText"],
                "enText": card["enText"],
                "parameters": style,
                "editable": True,
            }
        )
    if seen != set(case_captions):
        missing = sorted(set(case_captions) - seen)
        raise PlanError("caption timeline is missing case captions: " + ", ".join(missing))
    result.sort(key=lambda item: (item["startFrame"], item["endFrame"], item["captionId"]))
    for order, item in enumerate(result):
        item["order"] = order
        item["planId"] = f"caption-{order:04d}"
    for segment_id in sorted({item["segmentId"] for item in result}):
        segment_cards = [item for item in result if item["segmentId"] == segment_id]
        scene = scenes_by_id[segment_id]
        cursor = scene["startFrame"]
        for card in segment_cards:
            if card["startFrame"] != cursor:
                raise PlanError(f"caption cards have a gap or overlap in scene {segment_id}")
            cursor = card["endFrame"]
        if cursor != scene["endFrame"]:
            raise PlanError(f"caption cards do not cover all of scene {segment_id}")
    return result


def carousel_frame_counts(total: int, count: int, spec: dict[str, Any], label: str) -> list[int]:
    if count < 2:
        raise PlanError(f"{label} must contain at least two source items")
    explicit = spec.get("framesPerItem")
    if explicit is not None:
        if not isinstance(explicit, list) or len(explicit) != count:
            raise PlanError(f"{label}.framesPerItem must match the item count")
        values = [
            json_integer(value, f"{label}.framesPerItem[{index}]", minimum=1)
            for index, value in enumerate(explicit)
        ]
        if sum(values) != total:
            raise PlanError(f"{label}.framesPerItem must sum to the scene frame count")
        return values
    if spec.get("itemFrames") is not None:
        value = json_integer(spec["itemFrames"], f"{label}.itemFrames", minimum=1)
        if value * count != total:
            raise PlanError(f"{label}.itemFrames times item count must equal scene frames")
        return [value] * count
    base, remainder = divmod(total, count)
    if base <= 0:
        raise PlanError(f"{label} has fewer frames than source items")
    return [base + (1 if index < remainder else 0) for index in range(count)]


def primary_and_overlay_items(
    project: Path,
    scenes: list[dict[str, Any]],
    scene_assets: dict[str, Any],
    canvas: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary: list[dict[str, Any]] = []
    overlays: list[dict[str, Any]] = []
    for scene_order, scene in enumerate(scenes):
        scene_id = scene["id"]
        spec = scene_assets.get(scene_id)
        if not isinstance(spec, dict):
            raise PlanError(f"render manifest has no object sceneAssets entry for {scene_id}")
        scene_type = spec.get("type")
        if scene_type not in ALLOWED_SCENE_TYPES:
            raise PlanError(f"scene {scene_id} has unsupported type: {scene_type!r}")
        start = scene["startFrame"]
        end = scene["endFrame"]
        frames = end - start
        label = f"sceneAssets.{scene_id}"
        raw_overlays = spec.get("overlays") or []
        if not isinstance(raw_overlays, list):
            raise PlanError(f"{label}.overlays must be a list")
        if raw_overlays and scene_type != "image":
            raise PlanError(f"{label}.overlays are supported only for image scenes")

        if scene_type in {"image", "video"}:
            relative, _path, digest = relative_file(
                project, spec.get("path"), f"{label}.path", reject_generated_media=True
            )
            fit = spec.get("fit", "cover")
            if fit not in ALLOWED_FIT_MODES:
                raise PlanError(f"{label}.fit is unsupported: {fit!r}")
            if scene_type == "image":
                motion = spec.get("motion") or "none"
                if motion not in {"none", "slow-zoom"}:
                    raise PlanError(f"{label}.motion is unsupported: {motion!r}")
                parameters: dict[str, Any] = {"fit": fit, "motion": motion}
                if motion == "slow-zoom":
                    parameters["zoomStep"] = renderer_number(
                        spec, "zoomStep", 0.0001, label, 0.0
                    )
                    parameters["zoomLimit"] = renderer_number(
                        spec, "zoomLimit", 1.04, label, 1.0
                    )
            else:
                parameters = {
                    "fit": fit,
                    "loop": exact_bool(spec.get("loop", True), f"{label}.loop"),
                    "startSeconds": optional_number(spec, "startSeconds", 0.0, label, 0.0),
                }
                source_duration = media_duration_seconds(_path)
                if parameters["startSeconds"] >= source_duration:
                    raise PlanError(
                        f"{label}.startSeconds is outside its source duration"
                    )
                required_end = parameters["startSeconds"] + frames / canvas["fps"]
                if not parameters["loop"] and required_end > source_duration + 1e-6:
                    raise PlanError(
                        f"{label} does not contain enough source duration for its frame range"
                    )
                parameters["sourceDurationSeconds"] = round(source_duration, 9)
            primary.append(
                {
                    "planId": f"primary-{scene_order:04d}-0000",
                    "order": len(primary),
                    "sceneOrder": scene_order,
                    "sceneId": scene_id,
                    "manifestType": scene_type,
                    "manifestIndex": 0,
                    "trackRole": "primary-visuals",
                    "startFrame": start,
                    "endFrame": end,
                    "sourcePath": relative,
                    "sourceSha256": digest,
                    "effectiveParameters": parameters,
                    "editable": True,
                }
            )
        elif scene_type == "carousel":
            raw_items = spec.get("items")
            if not isinstance(raw_items, list):
                raise PlanError(f"{label}.items must be a list")
            counts = carousel_frame_counts(frames, len(raw_items), spec, label)
            parameters = {
                "maxWidth": renderer_integer(
                    spec, "maxWidth", round(canvas["width"] * 0.58), label, 1
                ),
                "maxHeight": renderer_integer(
                    spec, "maxHeight", round(canvas["height"] * 0.55), label, 1
                ),
                "framePadding": renderer_integer(spec, "framePadding", 36, label, 0),
                "backgroundColor": str(spec.get("backgroundColor") or "0xf3eadb"),
                "itemCount": len(raw_items),
            }
            cursor = start
            for manifest_index, (raw_path, count) in enumerate(zip(raw_items, counts)):
                relative, _path, digest = relative_file(
                    project,
                    raw_path,
                    f"{label}.items[{manifest_index}]",
                    reject_generated_media=True,
                )
                item_end = cursor + count
                primary.append(
                    {
                        "planId": f"primary-{scene_order:04d}-{manifest_index:04d}",
                        "order": len(primary),
                        "sceneOrder": scene_order,
                        "sceneId": scene_id,
                        "manifestType": scene_type,
                        "manifestIndex": manifest_index,
                        "trackRole": "primary-visuals",
                        "startFrame": cursor,
                        "endFrame": item_end,
                        "sourcePath": relative,
                        "sourceSha256": digest,
                        "effectiveParameters": parameters,
                        "editable": True,
                    }
                )
                cursor = item_end
            if cursor != end:
                raise PlanError(f"{label} item ranges do not cover the scene")
        else:
            color = spec.get("color") or "black"
            if not isinstance(color, str) or not color.strip():
                raise PlanError(f"{label}.color must be a non-empty string")
            primary.append(
                {
                    "planId": f"primary-{scene_order:04d}-0000",
                    "order": len(primary),
                    "sceneOrder": scene_order,
                    "sceneId": scene_id,
                    "manifestType": scene_type,
                    "manifestIndex": 0,
                    "trackRole": "primary-visuals",
                    "startFrame": start,
                    "endFrame": end,
                    "sourcePath": "",
                    "sourceSha256": "",
                    "effectiveParameters": {"color": color.strip()},
                    "editable": True,
                }
            )

        for manifest_index, overlay in enumerate(raw_overlays):
            if not isinstance(overlay, dict):
                raise PlanError(f"{label}.overlays[{manifest_index}] must be an object")
            relative, _path, digest = relative_file(
                project,
                overlay.get("path"),
                f"{label}.overlays[{manifest_index}].path",
                reject_generated_media=True,
            )
            x = overlay.get("x", "(W-w)/2")
            y = overlay.get("y", "(H-h)/2")
            role = overlay.get("layerRole", "overlay")
            for value, field in ((x, "x"), (y, "y"), (role, "layerRole")):
                if not isinstance(value, str) or not value.strip():
                    raise PlanError(
                        f"{label}.overlays[{manifest_index}].{field} must be a non-empty string"
                    )
            overlays.append(
                {
                    "planId": f"overlay-{scene_order:04d}-{manifest_index:04d}",
                    "order": len(overlays),
                    "sceneOrder": scene_order,
                    "sceneId": scene_id,
                    "manifestIndex": manifest_index,
                    "trackRole": "overlays",
                    "startFrame": start,
                    "endFrame": end,
                    "sourcePath": relative,
                    "sourceSha256": digest,
                    "layerRole": role.strip(),
                    "x": x.strip(),
                    "y": y.strip(),
                    "width": optional_integer(overlay, "width", 0, f"{label}.overlays[{manifest_index}]", 0),
                    "height": optional_integer(overlay, "height", 0, f"{label}.overlays[{manifest_index}]", 0),
                    "fadeInSeconds": optional_number(
                        overlay,
                        "fadeInSeconds",
                        0.0,
                        f"{label}.overlays[{manifest_index}]",
                        0.0,
                    ),
                    "editable": True,
                }
            )
    return primary, overlays


def media_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as source:
            if source.getframerate() <= 0:
                raise PlanError(f"audio source has an invalid sample rate: {path}")
            return source.getnframes() / source.getframerate()
    except (wave.Error, EOFError):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise PlanError(
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
        if result.returncode != 0:
            raise PlanError(f"cannot determine audio duration: {path}")
        try:
            duration = float(result.stdout.strip())
        except ValueError as exc:
            raise PlanError(f"cannot determine audio duration: {path}") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise PlanError(f"cannot determine audio duration: {path}")
        return duration


def audio_items(
    project: Path,
    manifest: dict[str, Any],
    alignment: dict[str, Any],
    fps: int,
    total_frames: int,
) -> list[dict[str, Any]]:
    if alignment.get("status") != "verified":
        raise PlanError("alignment report status must be verified")
    timestamp_source = alignment.get("timestampSource")
    if not isinstance(timestamp_source, str) or not timestamp_source.strip():
        raise PlanError("alignment report timestampSource must be a non-empty string")
    if alignment.get("providerRequestCount") != 1:
        raise PlanError("alignment report providerRequestCount must equal 1")
    if alignment.get("providerAttemptCount") != 1:
        raise PlanError("alignment report providerAttemptCount must equal 1")
    if alignment.get("textCoverage") != 1.0:
        raise PlanError("alignment report textCoverage must equal 1.0")
    audio = manifest.get("audio")
    if not isinstance(audio, dict):
        raise PlanError("render manifest audio must be an object")
    narration_path, _narration_file, narration_hash = relative_file(
        project, audio.get("narration"), "render manifest audio.narration"
    )
    alignment_audio, _alignment_file, alignment_audio_hash = relative_file(
        project, alignment.get("finalAudio"), "alignment report finalAudio"
    )
    if narration_path != alignment_audio:
        raise PlanError("manifest narration path differs from alignment report finalAudio")
    recorded_hash = alignment.get("finalAudioSha256")
    if not isinstance(recorded_hash, str) or recorded_hash != alignment_audio_hash:
        raise PlanError("alignment report finalAudioSha256 is missing or stale")
    narration_duration = media_duration_seconds(_narration_file)
    narration_frames = math.ceil(narration_duration * fps - 1e-9)
    if narration_frames != total_frames:
        raise PlanError(
            "aligned narration duration does not match scene timeline totalFrames: "
            f"{narration_frames} != {total_frames}"
        )
    result = [
        {
            "planId": "audio-narration-0000",
            "order": 0,
            "role": "narration",
            "manifestIndex": 0,
            "trackRole": "narration",
            "startFrame": 0,
            "endFrame": total_frames,
            "sourcePath": narration_path,
            "sourceSha256": narration_hash,
            "volume": renderer_number(audio, "narrationVolume", 1.0, "render manifest audio", 0.0),
            "fadeInSeconds": 0.0,
            "fadeOutSeconds": 0.0,
            "editable": True,
        }
    ]
    bgm = audio.get("bgm") or {}
    if not isinstance(bgm, dict):
        raise PlanError("render manifest audio.bgm must be an object")
    if bgm.get("path"):
        relative, _path, digest = relative_file(
            project, bgm.get("path"), "render manifest audio.bgm.path"
        )
        result.append(
            {
                "planId": "audio-bgm-0000",
                "order": len(result),
                "role": "bgm",
                "manifestIndex": 0,
                "trackRole": "bgm",
                "startFrame": 0,
                "endFrame": total_frames,
                "sourcePath": relative,
                "sourceSha256": digest,
                "volume": renderer_number(bgm, "volume", 0.035, "render manifest audio.bgm", 0.0),
                "fadeInSeconds": optional_number(
                    bgm, "fadeInSeconds", 0.0, "render manifest audio.bgm", 0.0
                ),
                "fadeOutSeconds": optional_number(
                    bgm, "fadeOutSeconds", 0.0, "render manifest audio.bgm", 0.0
                ),
                "loopToTimelineEnd": True,
                "editable": True,
            }
        )
    raw_sfx = audio.get("sfx") or []
    if not isinstance(raw_sfx, list):
        raise PlanError("render manifest audio.sfx must be a list")
    for manifest_index, spec in enumerate(raw_sfx):
        label = f"render manifest audio.sfx[{manifest_index}]"
        if not isinstance(spec, dict):
            raise PlanError(f"{label} must be an object")
        relative, source, digest = relative_file(project, spec.get("path"), f"{label}.path")
        if spec.get("startFrame") is not None:
            start = json_integer(spec.get("startFrame"), f"{label}.startFrame", minimum=0)
            start_basis: dict[str, Any] = {"mode": "startFrame", "value": start}
        elif spec.get("startSeconds") is not None:
            seconds = finite_number(spec.get("startSeconds"), f"{label}.startSeconds", minimum=0.0)
            delay_ms = round(seconds * 1000)
            start = round(delay_ms * fps / 1000)
            start_basis = {
                "mode": "startSeconds",
                "value": seconds,
                "roundedDelayMs": delay_ms,
            }
        else:
            raise PlanError(f"{label} needs startFrame or startSeconds")
        if start >= total_frames:
            raise PlanError(f"{label} starts outside the timeline at frame {start}")
        duration = media_duration_seconds(source)
        duration_frames = max(1, math.ceil(duration * fps - 1e-9))
        result.append(
            {
                "planId": f"audio-sfx-{manifest_index:04d}",
                "order": len(result),
                "role": "sfx",
                "manifestIndex": manifest_index,
                "trackRole": "sfx",
                "startFrame": start,
                "endFrame": min(total_frames, start + duration_frames),
                "sourcePath": relative,
                "sourceSha256": digest,
                "volume": renderer_number(spec, "volume", 1.0, label, 0.0),
                "fadeInSeconds": optional_number(spec, "fadeInSeconds", 0.0, label, 0.0),
                "fadeOutSeconds": optional_number(spec, "fadeOutSeconds", 0.0, label, 0.0),
                "sourceDurationSeconds": round(duration, 9),
                "sourceDurationFrames": duration_frames,
                "startBasis": start_basis,
                "editable": True,
            }
        )
    return result


def source_asset_index(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    indexed: dict[tuple[str, str], set[str]] = {}
    for items in groups:
        for item in items:
            path = item.get("sourcePath")
            digest = item.get("sourceSha256")
            if not path:
                continue
            key = (path, digest)
            indexed.setdefault(key, set()).add(item["planId"])
    return [
        {"path": path, "sha256": digest, "usedByPlanIds": sorted(plan_ids)}
        for (path, digest), plan_ids in sorted(indexed.items())
    ]


def operation_stages() -> list[dict[str, Any]]:
    definitions = [
        ("select-adapter", [], ["editor route and live schema"]),
        ("create-project", ["select-adapter"], ["projectId", "timelineId"]),
        ("import-source-assets", ["create-project"], ["adapter asset IDs"]),
        ("create-semantic-tracks", ["create-project"], ["adapter track IDs"]),
        (
            "place-primary-items",
            ["import-source-assets", "create-semantic-tracks"],
            ["primary planId to editor item mapping"],
        ),
        (
            "place-overlay-items",
            ["import-source-assets", "create-semantic-tracks"],
            ["overlay planId to editor item mapping"],
        ),
        (
            "place-caption-items",
            ["create-semantic-tracks"],
            ["caption planId to editor key mapping"],
        ),
        (
            "place-audio-items",
            ["import-source-assets", "create-semantic-tracks"],
            ["audio planId to editor item mapping"],
        ),
        (
            "save-project",
            [
                "place-primary-items",
                "place-overlay-items",
                "place-caption-items",
                "place-audio-items",
            ],
            ["saved project identity"],
        ),
        ("reopen-and-readback", ["save-project"], ["independent normalized readback JSON"]),
        (
            "capture-composed-frames",
            ["reopen-and-readback"],
            ["opening, middle, and ending PNG evidence"],
        ),
        (
            "write-delivery-ledger",
            ["reopen-and-readback", "capture-composed-frames"],
            ["editable-delivery.json pending independent validation"],
        ),
        (
            "validate-delivery",
            ["write-delivery-ledger"],
            ["validate_editable_delivery.py result"],
        ),
    ]
    return [
        {
            "order": order,
            "id": identifier,
            "status": "pending",
            "dependsOn": dependencies,
            "expectedOutputs": outputs,
        }
        for order, (identifier, dependencies, outputs) in enumerate(definitions)
    ]


def readback_contract(
    primary: list[dict[str, Any]],
    overlays: list[dict[str, Any]],
    captions: list[dict[str, Any]],
    audio: list[dict[str, Any]],
    total_frames: int,
) -> dict[str, Any]:
    return {
        "status": "required-not-captured",
        "mustReopenProject": True,
        "mustUseIndependentEditorResponse": True,
        "requiredIdentityFields": ["route", "projectId", "timelineId", "capturedAt"],
        "requiredIdKinds": ["assetIds", "trackIds", "itemIds", "captionKeys"],
        "expectedCounts": {
            "primaryItems": len(primary),
            "overlayItems": len(overlays),
            "captionItems": len(captions),
            "audioItems": len(audio),
        },
        "requiredPlanIds": {
            "primaryItems": [item["planId"] for item in primary],
            "overlayItems": [item["planId"] for item in overlays],
            "captionItems": [item["planId"] for item in captions],
            "audioItems": [item["planId"] for item in audio],
        },
        "verificationFrames": [
            {"position": "opening", "allowedFrameRange": [0, total_frames // 3]},
            {
                "position": "middle",
                "allowedFrameRange": [total_frames // 3, (2 * total_frames) // 3],
            },
            {
                "position": "ending",
                "allowedFrameRange": [(2 * total_frames) // 3, total_frames - 1],
            },
        ],
        "deliveryValidator": "scripts/validate_editable_delivery.py",
    }


def build_editor_plan(project: Path) -> dict[str, Any]:
    project = project.resolve()
    if not project.is_dir():
        raise PlanError(f"project directory does not exist: {project}")
    input_paths = {
        "case": project / "case.json",
        "renderManifest": project / "render-manifest.json",
        "sceneTimeline": project / "timing/scene-timeline.json",
        "captionTimeline": project / "timing/caption-timeline.json",
        "alignmentReport": project / "timing/alignment-report.json",
    }
    case = load_json(input_paths["case"], "case.json")
    manifest = load_json(input_paths["renderManifest"], "render-manifest.json")
    scene_document = load_json(input_paths["sceneTimeline"], "scene timeline")
    caption_document = load_json(input_paths["captionTimeline"], "caption timeline")
    alignment = load_json(input_paths["alignmentReport"], "alignment report")

    if case.get("status") not in {"approved", "approved-for-generation", "ready"}:
        raise PlanError("case status must be approved before editor planning")

    canvas = require_canvas(case, "case")
    if require_canvas(manifest, "render manifest") != canvas:
        raise PlanError("case and render manifest canvases differ")
    scenes, total_frames = ordered_scenes(scene_document, canvas["fps"])
    expected_scene_ids, case_captions = case_scene_ids(case)
    actual_scene_ids = {scene["id"] for scene in scenes}
    if actual_scene_ids != expected_scene_ids:
        missing = sorted(expected_scene_ids - actual_scene_ids)
        extra = sorted(actual_scene_ids - expected_scene_ids)
        raise PlanError(
            "scene timeline differs from case scene/hold ids"
            + (f"; missing={missing}" if missing else "")
            + (f"; extra={extra}" if extra else "")
        )
    raw_assets = manifest.get("sceneAssets")
    if not isinstance(raw_assets, dict):
        raise PlanError("render manifest sceneAssets must be an object")
    if set(raw_assets) != actual_scene_ids:
        missing = sorted(actual_scene_ids - set(raw_assets))
        extra = sorted(set(raw_assets) - actual_scene_ids)
        raise PlanError(
            "render manifest sceneAssets differs from the scene timeline"
            + (f"; missing={missing}" if missing else "")
            + (f"; extra={extra}" if extra else "")
        )
    primary, overlays = primary_and_overlay_items(
        project, scenes, raw_assets, canvas
    )
    style = caption_style(manifest, canvas)
    scenes_by_id = {scene["id"]: scene for scene in scenes}
    captions = ordered_captions(
        caption_document,
        case_captions,
        scenes_by_id,
        canvas["fps"],
        total_frames,
        style,
    )
    audio = audio_items(project, manifest, alignment, canvas["fps"], total_frames)
    input_sources = {
        name: {
            "path": path.relative_to(project).as_posix(),
            "sha256": sha256(path),
        }
        for name, path in sorted(input_paths.items())
    }
    return {
        "version": PLAN_VERSION,
        "contract": PLAN_CONTRACT,
        "status": "planned-not-executed",
        "adapterNeutral": True,
        "editorExecutionClaimed": False,
        "canvas": canvas,
        "timing": {
            "fps": canvas["fps"],
            "totalFrames": total_frames,
            "durationSeconds": round(total_frames / canvas["fps"], 9),
            "timestampSource": alignment.get("timestampSource"),
            "providerRequestCount": alignment.get("providerRequestCount"),
            "providerAttemptCount": alignment.get("providerAttemptCount"),
        },
        "inputSources": input_sources,
        "sourceAssets": source_asset_index([primary, overlays, audio]),
        "trackRoles": [
            {"order": 0, "role": "primary-visuals", "kind": "video"},
            {"order": 1, "role": "overlays", "kind": "video"},
            {"order": 2, "role": "captions", "kind": "text"},
            {"order": 3, "role": "narration", "kind": "audio"},
            {"order": 4, "role": "bgm", "kind": "audio"},
            {"order": 5, "role": "sfx", "kind": "audio"},
        ],
        "items": {
            "primaryScenes": primary,
            "overlays": overlays,
            "captions": captions,
            "audio": audio,
        },
        "operations": {
            "status": "not-started",
            "adapterMustTranslatePlanIds": True,
            "stages": operation_stages(),
        },
        "readback": readback_contract(
            primary, overlays, captions, audio, total_frames
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic adapter-neutral editor plan"
    )
    parser.add_argument("project", type=Path)
    parser.add_argument(
        "--output",
        default="editor-plan.json",
        help="project-relative output path (default: editor-plan.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        project = args.project.resolve()
        output = project_output_path(project, args.output)
        document = build_editor_plan(project)
        output_relative = output.relative_to(project).as_posix()
        bound_paths = {
            item["path"] for item in document["inputSources"].values()
        } | {item["path"] for item in document["sourceAssets"]}
        if output_relative in bound_paths:
            raise PlanError(f"--output would overwrite a bound input/source: {output_relative}")
        atomic_write_json(output, document)
    except (PlanError, OSError) as exc:
        print(f"editor plan failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "planStatus": document["status"],
                "output": output.relative_to(project).as_posix(),
                "primaryItems": len(document["items"]["primaryScenes"]),
                "overlayItems": len(document["items"]["overlays"]),
                "captionItems": len(document["items"]["captions"]),
                "audioItems": len(document["items"]["audio"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
