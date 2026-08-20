#!/usr/bin/env python3
"""Project-path safety and deterministic render-input provenance helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


RENDER_INPUT_INVENTORY_VERSION = 1
EDITABLE_DELIVERY_VERSION = 2
READBACK_EVIDENCE_VERSION = 2
DELIVERY_ROUTES = {"chatcut"}
DELIVERY_AUDIO_ROLES = {"narration", "bgm", "sfx"}
DELIVERY_SOURCE_FILES = {
    "caseSha256": "case.json",
    "renderManifestSha256": "render-manifest.json",
    "alignmentReportSha256": "timing/alignment-report.json",
    "sceneTimelineSha256": "timing/scene-timeline.json",
    "captionTimelineSha256": "timing/caption-timeline.json",
    "narrationAudioSha256": "timing/narration.timestamped.final.wav",
}
SCENE_MAPPING_FIELDS = (
    "sceneId",
    "itemId",
    "assetId",
    "trackId",
    "startFrame",
    "endFrame",
    "sourcePath",
    "sourceSha256",
    "editable",
)
OVERLAY_MAPPING_FIELDS = (
    "sceneId",
    "manifestIndex",
    "itemId",
    "assetId",
    "trackId",
    "startFrame",
    "endFrame",
    "sourcePath",
    "sourceSha256",
    "layerRole",
    "x",
    "y",
    "width",
    "height",
    "fadeInSeconds",
    "editable",
)
CAPTION_MAPPING_FIELDS = (
    "captionId",
    "editorKey",
    "trackId",
    "startFrame",
    "endFrame",
    "zhText",
    "enText",
    "editable",
)
AUDIO_MAPPING_FIELDS = (
    "role",
    "manifestIndex",
    "itemId",
    "assetId",
    "trackId",
    "startFrame",
    "endFrame",
    "sourcePath",
    "sourceSha256",
    "volume",
    "fadeInSeconds",
    "fadeOutSeconds",
    "editable",
)


class ProjectArtifactError(ValueError):
    """Raised when a project artifact is ambiguous, unsafe, or incomplete."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def secure_project_path(
    project: Path,
    value: Any,
    label: str,
    *,
    must_exist: bool = False,
    file_only: bool = False,
) -> Path:
    """Return one canonical in-project path while rejecting every symlink hop.

    Resolving a symlink and then checking containment is insufficient: an in-project
    symlink can silently substitute a different file, and an external symlink can
    expose data outside the project.  Inspect the lexical path first, reject every
    existing symlink component, then perform the containment check.
    """

    root = project.resolve()
    raw = str(value or "").strip()
    if not raw:
        raise ProjectArtifactError(f"{label} path is empty")
    relative = Path(raw)
    if relative.is_absolute():
        raise ProjectArtifactError(f"{label} must use a project-relative path")
    if ".." in relative.parts:
        raise ProjectArtifactError(
            f"{label} escapes the project directory via a parent path"
        )
    if any(part in {"", "."} for part in relative.parts):
        raise ProjectArtifactError(f"{label} must use a normalized project-relative path")

    lexical = root
    for part in relative.parts:
        lexical = lexical / part
        if lexical.is_symlink():
            raise ProjectArtifactError(f"{label} must not be a symlink: {relative.as_posix()}")

    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectArtifactError(f"{label} escapes the project directory") from exc

    if must_exist and not resolved.exists():
        raise ProjectArtifactError(f"{label} does not exist: {relative.as_posix()}")
    if file_only and not resolved.is_file():
        raise ProjectArtifactError(f"{label} is not a regular file: {relative.as_posix()}")
    return resolved


def secure_project_file(project: Path, value: Any, label: str) -> Path:
    return secure_project_path(
        project,
        value,
        label,
        must_exist=True,
        file_only=True,
    )


def project_relative(project: Path, path: Path) -> str:
    return path.relative_to(project.resolve()).as_posix()


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectArtifactError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ProjectArtifactError(f"{label} JSON root must be an object")
    return document


def inventory_sha256(entries: list[dict[str, str]]) -> str:
    payload = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inventory_entry(project: Path, role: str, value: Any) -> dict[str, str]:
    path = secure_project_file(project, value, f"render input {role}")
    return {
        "role": role,
        "path": project_relative(project, path),
        "sha256": file_sha256(path),
    }


def build_render_input_inventory(project: Path) -> dict[str, Any]:
    """Independently enumerate every project file consumed by render/validation."""

    project = project.resolve()
    case_path = secure_project_file(project, "case.json", "render input case.json")
    manifest_path = secure_project_file(
        project, "render-manifest.json", "render input render-manifest.json"
    )
    alignment_path = secure_project_file(
        project, "timing/alignment-report.json", "render input alignment report"
    )
    case = load_json_object(case_path, "case.json")
    manifest = load_json_object(manifest_path, "render manifest")
    alignment = load_json_object(alignment_path, "alignment report")

    entries: list[dict[str, str]] = [
        {
            "role": "control.case",
            "path": project_relative(project, case_path),
            "sha256": file_sha256(case_path),
        },
        {
            "role": "control.render-manifest",
            "path": project_relative(project, manifest_path),
            "sha256": file_sha256(manifest_path),
        },
        {
            "role": "timing.alignment-report",
            "path": project_relative(project, alignment_path),
            "sha256": file_sha256(alignment_path),
        },
        _inventory_entry(
            project, "timing.caption-timeline", "timing/caption-timeline.json"
        ),
        _inventory_entry(project, "timing.scene-timeline", "timing/scene-timeline.json"),
    ]

    captions = manifest.get("captions") or {}
    audio = manifest.get("audio") or {}
    if not isinstance(captions, dict):
        raise ProjectArtifactError("render manifest captions must be an object")
    if not isinstance(audio, dict):
        raise ProjectArtifactError("render manifest audio must be an object")
    entries.append(_inventory_entry(project, "captions.ass", captions.get("ass")))
    entries.append(_inventory_entry(project, "audio.narration", audio.get("narration")))

    bgm = audio.get("bgm") or {}
    if not isinstance(bgm, dict):
        raise ProjectArtifactError("render manifest audio.bgm must be an object")
    if str(bgm.get("path") or "").strip():
        entries.append(_inventory_entry(project, "audio.bgm", bgm.get("path")))
    sfx_values = audio.get("sfx") or []
    if not isinstance(sfx_values, list):
        raise ProjectArtifactError("render manifest audio.sfx must be a list")
    for index, sfx in enumerate(sfx_values):
        if not isinstance(sfx, dict):
            raise ProjectArtifactError(f"render manifest audio.sfx[{index}] must be an object")
        entries.append(_inventory_entry(project, f"audio.sfx[{index}]", sfx.get("path")))

    scene_assets = manifest.get("sceneAssets") or {}
    if not isinstance(scene_assets, dict):
        raise ProjectArtifactError("render manifest sceneAssets must be an object")
    for scene_id in sorted(scene_assets):
        spec = scene_assets[scene_id]
        if not isinstance(spec, dict):
            raise ProjectArtifactError(f"render manifest sceneAssets.{scene_id} must be an object")
        scene_type = str(spec.get("type") or "")
        if scene_type in {"image", "video"}:
            entries.append(
                _inventory_entry(project, f"scene.{scene_id}.primary", spec.get("path"))
            )
        elif scene_type == "carousel":
            items = spec.get("items") or []
            if not isinstance(items, list):
                raise ProjectArtifactError(f"carousel scene {scene_id} items must be a list")
            for index, value in enumerate(items):
                entries.append(
                    _inventory_entry(project, f"scene.{scene_id}.carousel[{index}]", value)
                )
        elif scene_type != "solid":
            raise ProjectArtifactError(f"scene {scene_id} has unsupported type: {scene_type}")

        overlays = spec.get("overlays") or []
        if not isinstance(overlays, list):
            raise ProjectArtifactError(f"scene {scene_id} overlays must be a list")
        for index, overlay in enumerate(overlays):
            if not isinstance(overlay, dict):
                raise ProjectArtifactError(f"scene {scene_id} overlay {index} must be an object")
            entries.append(
                _inventory_entry(
                    project,
                    f"scene.{scene_id}.overlay[{index}]",
                    overlay.get("path"),
                )
            )
        if str(spec.get("sourceRecord") or "").strip():
            entries.append(
                _inventory_entry(
                    project,
                    f"scene.{scene_id}.source-record",
                    spec.get("sourceRecord"),
                )
            )

    for role, field in (
        ("provider.raw-narration", "rawNarrationAudio"),
        ("provider.tts-report", "ttsReport"),
        ("provider.word-timeline", "wordTimeline"),
    ):
        entries.append(_inventory_entry(project, role, alignment.get(field)))

    approval = case.get("approval") or {}
    receipt = approval.get("receipt") if isinstance(approval, dict) else None
    if isinstance(receipt, dict) and receipt:
        preview = receipt.get("voicePreview") or {}
        if not isinstance(preview, dict):
            raise ProjectArtifactError("approval receipt voicePreview must be an object")
        preview_report = preview.get("report") or {}
        if not isinstance(preview_report, dict):
            raise ProjectArtifactError("approval receipt voicePreview.report must be an object")
        package = receipt.get("approvalPackage") or {}
        if not isinstance(package, dict):
            raise ProjectArtifactError("approval receipt approvalPackage must be an object")
        entries.extend(
            [
                _inventory_entry(project, "approval.voice-preview", preview.get("path")),
                _inventory_entry(
                    project,
                    "approval.voice-preview-report",
                    preview_report.get("path"),
                ),
                _inventory_entry(project, "approval.package", package.get("path")),
            ]
        )

    entries.sort(key=lambda item: (item["role"], item["path"]))
    roles = [item["role"] for item in entries]
    if len(roles) != len(set(roles)):
        raise ProjectArtifactError("render input inventory contains duplicate roles")
    return {
        "version": RENDER_INPUT_INVENTORY_VERSION,
        "entries": entries,
        "sha256": inventory_sha256(entries),
    }


def compare_render_input_inventory(
    project: Path, recorded: Any
) -> tuple[dict[str, Any] | None, list[str]]:
    """Rebuild the inventory from current controls and compare every role/path/hash."""

    errors: list[str] = []
    if not isinstance(recorded, dict):
        return None, ["render input inventory is missing or not an object"]
    if recorded.get("version") != RENDER_INPUT_INVENTORY_VERSION:
        errors.append(
            f"render input inventory version must be {RENDER_INPUT_INVENTORY_VERSION}"
        )
    recorded_entries = recorded.get("entries")
    if not isinstance(recorded_entries, list):
        return None, errors + ["render input inventory entries must be a list"]
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(recorded_entries):
        if not isinstance(item, dict):
            errors.append(f"render input inventory entry {index} must be an object")
            continue
        role = str(item.get("role") or "").strip()
        path = str(item.get("path") or "").strip()
        digest = str(item.get("sha256") or "").strip()
        if not role or not path or len(digest) != 64:
            errors.append(f"render input inventory entry {index} is incomplete")
            continue
        normalized.append({"role": role, "path": path, "sha256": digest})
    if normalized != sorted(normalized, key=lambda item: (item["role"], item["path"])):
        errors.append("render input inventory entries are not in canonical order")
    roles = [item["role"] for item in normalized]
    if len(roles) != len(set(roles)):
        errors.append("render input inventory contains duplicate roles")
    recorded_digest = inventory_sha256(normalized)
    if str(recorded.get("sha256") or "") != recorded_digest:
        errors.append("render input inventory sha256 is missing or stale")

    try:
        current = build_render_input_inventory(project)
    except ProjectArtifactError as exc:
        errors.append(f"render input inventory cannot be rebuilt: {exc}")
        return None, errors

    recorded_by_role = {item["role"]: item for item in normalized}
    current_by_role = {item["role"]: item for item in current["entries"]}
    for role in sorted(recorded_by_role.keys() - current_by_role.keys()):
        errors.append(f"render input inventory has stale role: {role}")
    for role in sorted(current_by_role.keys() - recorded_by_role.keys()):
        errors.append(f"render input inventory is missing role: {role}")
    for role in sorted(recorded_by_role.keys() & current_by_role.keys()):
        old = recorded_by_role[role]
        new = current_by_role[role]
        if old["path"] != new["path"]:
            errors.append(f"render input inventory path changed for {role}")
        if old["sha256"] != new["sha256"]:
            errors.append(
                f"render input inventory source hash changed for {role}: {new['path']}"
            )
    if recorded.get("sha256") != current.get("sha256"):
        errors.append("render input inventory differs from the files used for the render")
    return current, list(dict.fromkeys(errors))
