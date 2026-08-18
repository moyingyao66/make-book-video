#!/usr/bin/env python3
"""Bind live editor IDs to the deterministic editor plan.

The model supplies only what the editor actually returned: project/timeline
identity, one track ID per semantic track role, and one editor ID per
``planId``. Every other field of ``editable-delivery.json`` and of the readback
evidence JSON is projected from ``editor-plan.json`` and the frozen timing
artifacts, so caption text, frame ranges, source paths, and SHA-256 values are
never retyped by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from project_artifacts import (
    AUDIO_MAPPING_FIELDS,
    CAPTION_MAPPING_FIELDS,
    DELIVERY_ROUTES,
    DELIVERY_SOURCE_FILES,
    EDITABLE_DELIVERY_VERSION,
    OVERLAY_MAPPING_FIELDS,
    ProjectArtifactError,
    READBACK_EVIDENCE_VERSION,
    SCENE_MAPPING_FIELDS,
    file_sha256,
    load_json_object,
    secure_project_file,
    secure_project_path,
)

BINDING_VERSION = 1
DEFAULT_BINDING = "editor-binding.json"
DEFAULT_EVIDENCE = "renders/qa/editor-readback.json"
ITEM_GROUPS = (
    ("primaryScenes", "sceneItems", SCENE_MAPPING_FIELDS, ("itemId", "assetId")),
    ("overlays", "overlayItems", OVERLAY_MAPPING_FIELDS, ("itemId", "assetId")),
    ("captions", "captionItems", CAPTION_MAPPING_FIELDS, ("editorKey",)),
    ("audio", "audioItems", AUDIO_MAPPING_FIELDS, ("itemId", "assetId")),
)


class BindingError(ValueError):
    """Raised when the plan, the binding, or the editor response is unusable."""


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    )
    try:
        with handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BindingError(f"{label} must be a non-empty string")
    return value


def load_plan(project: Path) -> dict[str, Any]:
    try:
        plan = load_json_object(project / "editor-plan.json", "editor-plan.json")
    except (OSError, ProjectArtifactError) as exc:
        raise BindingError(
            f"editor-plan.json is missing or unreadable ({exc}); "
            "run scripts/build_editor_plan.py first"
        ) from exc
    if plan.get("editorExecutionClaimed") is not False:
        raise BindingError("editor-plan.json must not claim editor execution")
    sources = plan.get("inputSources")
    if not isinstance(sources, dict) or not sources:
        raise BindingError("editor-plan.json has no inputSources")
    stale = []
    for name, entry in sorted(sources.items()):
        if not isinstance(entry, dict):
            raise BindingError(f"editor-plan.json inputSources.{name} must be an object")
        try:
            path = secure_project_file(
                project, entry.get("path"), f"editor plan inputSources.{name}.path"
            )
        except ProjectArtifactError as exc:
            raise BindingError(str(exc)) from exc
        if file_sha256(path) != entry.get("sha256"):
            stale.append(name)
    if stale:
        raise BindingError(
            "editor-plan.json is stale for: "
            + ", ".join(stale)
            + "; rerun scripts/build_editor_plan.py before binding"
        )
    return plan


def plan_items(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    items = plan.get("items")
    if not isinstance(items, dict):
        raise BindingError("editor-plan.json items must be an object")
    result: dict[str, list[dict[str, Any]]] = {}
    for group, _target, _fields, _ids in ITEM_GROUPS:
        entries = items.get(group)
        if not isinstance(entries, list):
            raise BindingError(f"editor-plan.json items.{group} must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("planId"), str):
                raise BindingError(f"editor-plan.json items.{group} entry is malformed")
        result[group] = entries
    return result


def binding_template(plan: dict[str, Any]) -> dict[str, Any]:
    grouped = plan_items(plan)
    roles = sorted(
        {
            str(entry.get("trackRole"))
            for entries in grouped.values()
            for entry in entries
        }
    )
    items: dict[str, Any] = {}
    for group, _target, _fields, id_fields in ITEM_GROUPS:
        for entry in grouped[group]:
            items[entry["planId"]] = {field: "" for field in id_fields}
    return {
        "version": BINDING_VERSION,
        "route": "openchatcut-local",
        "projectId": "",
        "timelineId": "",
        "editorUrl": "",
        "readback": {"source": "", "capturedAt": ""},
        "trackIds": {role: "" for role in roles},
        "items": items,
        "verificationFrames": [
            {"frame": None, "evidencePath": "", "notes": ""} for _ in range(3)
        ],
    }


def collect_strings(value: Any, into: set[str]) -> None:
    if isinstance(value, str):
        into.add(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            into.add(str(key))
            collect_strings(item, into)
    elif isinstance(value, list):
        for item in value:
            collect_strings(item, into)


def editor_response_strings(project: Path, values: Iterable[str]) -> tuple[set[str], list[dict[str, str]]]:
    strings: set[str] = set()
    records: list[dict[str, str]] = []
    for value in values:
        try:
            path = secure_project_file(project, value, "editor response path")
        except ProjectArtifactError as exc:
            raise BindingError(str(exc)) from exc
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BindingError(f"editor response {value} is invalid JSON: {exc}") from exc
        collect_strings(payload, strings)
        records.append(
            {
                "path": path.relative_to(project).as_posix(),
                "sha256": file_sha256(path),
            }
        )
    return strings, records


def verification_section(frame: int, total_frames: int) -> str:
    if frame * 3 < total_frames:
        return "opening"
    if frame * 3 < total_frames * 2:
        return "middle"
    return "ending"


def build_verification_frames(
    project: Path, binding: dict[str, Any], total_frames: int
) -> list[dict[str, Any]]:
    raw = binding.get("verificationFrames")
    if not isinstance(raw, list) or len(raw) < 3:
        raise BindingError(
            "binding verificationFrames must list at least three composed-frame checks"
        )
    frames: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        label = f"binding verificationFrames[{index}]"
        if not isinstance(entry, dict):
            raise BindingError(f"{label} must be an object")
        frame = entry.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool):
            raise BindingError(f"{label}.frame must be an integer")
        if not 0 <= frame < total_frames:
            raise BindingError(f"{label}.frame is outside the timeline")
        try:
            path = secure_project_file(
                project, entry.get("evidencePath"), f"{label}.evidencePath"
            )
        except ProjectArtifactError as exc:
            raise BindingError(str(exc)) from exc
        if path.suffix.lower() != ".png":
            raise BindingError(f"{label}.evidencePath must be a .png file")
        notes = entry.get("notes", "")
        if not isinstance(notes, str):
            raise BindingError(f"{label}.notes must be a string")
        frames.append(
            {
                "position": verification_section(frame, total_frames),
                "frame": frame,
                "evidencePath": path.relative_to(project).as_posix(),
                "sha256": file_sha256(path),
                "notes": notes,
            }
        )
    sections = {frame["position"] for frame in frames}
    missing = {"opening", "middle", "ending"} - sections
    if missing:
        raise BindingError(
            "verification frames must cover opening, middle, and ending; missing: "
            + ", ".join(sorted(missing))
        )
    if len({frame["frame"] for frame in frames}) < 3:
        raise BindingError("verification frames must use at least three distinct frames")
    duplicate_paths = sorted(
        {
            frame["evidencePath"]
            for frame in frames
            if [item["evidencePath"] for item in frames].count(frame["evidencePath"]) > 1
        }
    )
    if duplicate_paths:
        raise BindingError(
            "verification frames must use distinct PNG files: " + ", ".join(duplicate_paths)
        )
    return frames


def build_mappings(
    plan: dict[str, Any],
    binding: dict[str, Any],
    known_strings: set[str] | None,
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    grouped = plan_items(plan)
    raw_items = binding.get("items")
    if not isinstance(raw_items, dict):
        raise BindingError("binding items must be an object keyed by planId")
    raw_tracks = binding.get("trackIds")
    if not isinstance(raw_tracks, dict):
        raise BindingError("binding trackIds must be an object keyed by track role")

    expected_ids = {
        entry["planId"] for entries in grouped.values() for entry in entries
    }
    missing = sorted(expected_ids - set(raw_items))
    extra = sorted(set(raw_items) - expected_ids)
    if missing:
        raise BindingError("binding items is missing planIds: " + ", ".join(missing))
    if extra:
        raise BindingError("binding items has unknown planIds: " + ", ".join(extra))

    used_ids: set[str] = set()
    mappings: dict[str, list[dict[str, Any]]] = {
        target: [] for _group, target, _fields, _ids in ITEM_GROUPS
    }
    for group, target, fields, id_fields in ITEM_GROUPS:
        for entry in grouped[group]:
            plan_id = entry["planId"]
            supplied = raw_items[plan_id]
            if not isinstance(supplied, dict):
                raise BindingError(f"binding items.{plan_id} must be an object")
            unknown = sorted(set(supplied) - set(id_fields))
            if unknown:
                raise BindingError(
                    f"binding items.{plan_id} has unsupported fields: " + ", ".join(unknown)
                )
            role = entry.get("trackRole")
            if not isinstance(role, str) or not role:
                raise BindingError(f"editor plan {plan_id} has no trackRole")
            track_id = exact_text(raw_tracks.get(role), f"binding trackIds.{role}")
            mapping: dict[str, Any] = {}
            for field in fields:
                if field == "trackId":
                    mapping[field] = track_id
                elif field in id_fields:
                    mapping[field] = exact_text(
                        supplied.get(field), f"binding items.{plan_id}.{field}"
                    )
                elif field == "editable":
                    mapping[field] = True
                else:
                    if field not in entry:
                        raise BindingError(
                            f"editor plan {plan_id} is missing {field}; rebuild the plan"
                        )
                    mapping[field] = entry[field]
            used_ids.add(track_id)
            for field in id_fields:
                used_ids.add(mapping[field])
            mappings[target].append(mapping)

    unknown_roles = sorted(set(raw_tracks) - {
        str(entry.get("trackRole"))
        for entries in grouped.values()
        for entry in entries
    })
    if unknown_roles:
        raise BindingError(
            "binding trackIds has unused track roles: " + ", ".join(unknown_roles)
        )

    if known_strings is not None:
        unseen = sorted(used_ids - known_strings)
        if unseen:
            raise BindingError(
                "these IDs do not appear in any recorded editor response: "
                + ", ".join(unseen)
            )
    return mappings, used_ids


def build_documents(
    project: Path,
    plan: dict[str, Any],
    binding: dict[str, Any],
    evidence_relative: str,
    status: str,
    editor_responses: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    route = exact_text(binding.get("route"), "binding route")
    if route not in DELIVERY_ROUTES:
        raise BindingError("binding route must be openchatcut-local or chatcut")
    project_id = exact_text(binding.get("projectId"), "binding projectId")
    timeline_id = exact_text(binding.get("timelineId"), "binding timelineId")
    editor_url = exact_text(binding.get("editorUrl"), "binding editorUrl")
    readback = binding.get("readback")
    if not isinstance(readback, dict):
        raise BindingError("binding readback must be an object")
    source = exact_text(readback.get("source"), "binding readback.source")
    captured_at = exact_text(readback.get("capturedAt"), "binding readback.capturedAt")

    known_strings: set[str] | None = None
    response_records: list[dict[str, str]] = []
    if editor_responses:
        known_strings, response_records = editor_response_strings(
            project, editor_responses
        )
        for value, label in ((project_id, "projectId"), (timeline_id, "timelineId")):
            if value not in known_strings:
                raise BindingError(
                    f"binding {label} does not appear in any recorded editor response"
                )
    elif status == "verified":
        raise BindingError(
            "a verified delivery requires at least one --editor-response capture"
        )

    mappings, _used = build_mappings(plan, binding, known_strings)

    canvas = plan.get("canvas")
    if not isinstance(canvas, dict):
        raise BindingError("editor-plan.json canvas must be an object")
    timing = plan.get("timing")
    if not isinstance(timing, dict) or not isinstance(timing.get("totalFrames"), int):
        raise BindingError("editor-plan.json timing.totalFrames must be an integer")
    total_frames = timing["totalFrames"]

    source_hashes: dict[str, str] = {}
    for field, relative in DELIVERY_SOURCE_FILES.items():
        try:
            path = secure_project_file(project, relative, f"delivery source {relative}")
        except ProjectArtifactError as exc:
            raise BindingError(str(exc)) from exc
        source_hashes[field] = file_sha256(path)

    frames = build_verification_frames(project, binding, total_frames)

    delivery_canvas = {
        "width": canvas.get("width"),
        "height": canvas.get("height"),
        "fps": canvas.get("fps"),
    }
    evidence = {
        "version": READBACK_EVIDENCE_VERSION,
        "source": source,
        "capturedAt": captured_at,
        "projectReopened": True,
        "projectId": project_id,
        "timelineId": timeline_id,
        "canvas": delivery_canvas,
        "assetIds": sorted(
            {
                mapping["assetId"]
                for target in ("sceneItems", "overlayItems", "audioItems")
                for mapping in mappings[target]
            }
        ),
        "trackIds": sorted(
            {
                mapping["trackId"]
                for target in mappings
                for mapping in mappings[target]
            }
        ),
        "itemIds": sorted(
            {
                mapping["itemId"]
                for target in ("sceneItems", "overlayItems", "audioItems")
                for mapping in mappings[target]
            }
        ),
        "captionKeys": sorted(
            {mapping["editorKey"] for mapping in mappings["captionItems"]}
        ),
        "sceneItems": mappings["sceneItems"],
        "overlayItems": mappings["overlayItems"],
        "captionItems": mappings["captionItems"],
        "audioItems": mappings["audioItems"],
        "editorResponses": response_records,
    }
    delivery = {
        "version": EDITABLE_DELIVERY_VERSION,
        "status": status,
        "route": route,
        "projectId": project_id,
        "timelineId": timeline_id,
        "editorUrl": editor_url,
        "canvas": delivery_canvas,
        "sourceHashes": source_hashes,
        "assembly": {
            "flattenedPrimaryInput": False,
            "sceneItems": mappings["sceneItems"],
            "overlayItems": mappings["overlayItems"],
            "captionItems": mappings["captionItems"],
            "audioItems": mappings["audioItems"],
        },
        "readback": {
            "source": source,
            "capturedAt": captured_at,
            "projectReopened": True,
            "projectId": project_id,
            "timelineId": timeline_id,
            "evidencePath": evidence_relative,
            "sha256": "",
        },
        "verificationFrames": frames,
        "optionalEditorExport": {"path": "", "sha256": ""},
        "notes": binding.get("notes", "") if isinstance(binding.get("notes"), str) else "",
    }
    return delivery, evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument(
        "--binding",
        default=DEFAULT_BINDING,
        help=f"project-relative editor ID binding (default: {DEFAULT_BINDING})",
    )
    parser.add_argument(
        "--editor-response",
        action="append",
        default=[],
        metavar="PATH",
        help="project-relative JSON captured from the live editor; repeatable",
    )
    parser.add_argument(
        "--evidence-output",
        default=DEFAULT_EVIDENCE,
        help=f"project-relative readback evidence path (default: {DEFAULT_EVIDENCE})",
    )
    parser.add_argument(
        "--status",
        choices=("pending", "verified"),
        default="pending",
        help="set verified only after inspecting the reopened project and frames",
    )
    parser.add_argument(
        "--emit-binding-template",
        action="store_true",
        help="write an empty binding skeleton for the current plan and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    try:
        plan = load_plan(project)
        binding_path = secure_project_path(
            project, args.binding, "binding path", must_exist=False
        )
        if args.emit_binding_template:
            atomic_write_json(binding_path, binding_template(plan))
            print(
                json.dumps(
                    {
                        "status": "template",
                        "binding": binding_path.relative_to(project).as_posix(),
                        "planItems": sum(
                            len(entries) for entries in plan_items(plan).values()
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if not binding_path.is_file():
            raise BindingError(
                f"binding file not found: {args.binding}; "
                "run with --emit-binding-template to create one"
            )
        binding = load_json_object(binding_path, "binding")
        evidence_path = secure_project_path(
            project, args.evidence_output, "evidence output path", must_exist=False
        )
        evidence_relative = evidence_path.relative_to(project).as_posix()
        delivery_path = project / "editable-delivery.json"
        bound = {entry["path"] for entry in plan.get("inputSources", {}).values()}
        bound |= {entry["path"] for entry in plan.get("sourceAssets", [])}
        for candidate in (evidence_relative, "editable-delivery.json"):
            if candidate in bound:
                raise BindingError(f"refusing to overwrite a bound input: {candidate}")
        delivery, evidence = build_documents(
            project,
            plan,
            binding,
            evidence_relative,
            args.status,
            args.editor_response,
        )
        atomic_write_json(evidence_path, evidence)
        delivery["readback"]["sha256"] = file_sha256(evidence_path)
        atomic_write_json(delivery_path, delivery)
    except (BindingError, ProjectArtifactError, OSError) as exc:
        print(f"editor binding failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": delivery["status"],
                "route": delivery["route"],
                "evidence": evidence_relative,
                "sceneItems": len(delivery["assembly"]["sceneItems"]),
                "overlayItems": len(delivery["assembly"]["overlayItems"]),
                "captionItems": len(delivery["assembly"]["captionItems"]),
                "audioItems": len(delivery["assembly"]["audioItems"]),
                "verificationFrames": len(delivery["verificationFrames"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
