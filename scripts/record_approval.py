#!/usr/bin/env python3
"""Record a hash-bound user approval receipt for a version 3+ book-video case."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_approval_package import build_package
from validate_case import (
    APPROVAL_RECEIPT_CONTRACT,
    canonical_document_sha256,
    case_content_projection,
    file_sha256,
    is_timezone_aware_iso8601,
    render_manifest_semantic_projection,
    validate_approval_receipt,
    validate_caption_contract,
    validate_case,
    validate_visual_source_contract,
    validate_voice_preview_report_document,
    voice_config_projection,
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing required file: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return document


def project_file(project: Path, value: Path, label: str) -> Path:
    if value.is_absolute():
        raise ValueError(f"{label} must use a project-relative path")
    resolved = (project / value).resolve()
    try:
        resolved.relative_to(project)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the project directory") from exc
    return resolved


def validate_voice_preview(path: Path) -> None:
    if path.suffix.lower() != ".wav":
        raise ValueError("voice preview must be a WAV file")
    if not path.is_file():
        raise ValueError(f"voice preview does not exist: {path}")
    try:
        with wave.open(str(path), "rb") as source:
            if (
                source.getnframes() <= 0
                or source.getframerate() <= 0
                or source.getnchannels() <= 0
            ):
                raise ValueError("voice preview WAV contains no playable samples")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"voice preview is not a readable WAV: {exc}") from exc


def draft_validation_copy(case: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(case)
    document["status"] = "draft"
    approval = document.setdefault("approval", {})
    approval["contentApprovedByUser"] = False
    approval["storyboardApprovedByUser"] = False
    approval["paidGenerationAuthorized"] = False
    approval["receipt"] = {}
    return document


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    existing_mode = path.stat().st_mode & 0o777
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, existing_mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def record(
    project: Path,
    *,
    approved_by: str,
    approved_at: str,
    voice_preview_value: Path,
    voice_preview_report_value: Path,
    approval_package_value: Path,
) -> dict[str, Any]:
    project = project.resolve()
    case_path = project / "case.json"
    manifest_path = project / "render-manifest.json"
    case = load_json(case_path)
    manifest = load_json(manifest_path)
    if int(case.get("version") or 0) < 3:
        raise ValueError("record_approval.py is required only for version 3+ projects")
    if not approved_by.strip():
        raise ValueError("--approved-by must be non-empty")
    if not is_timezone_aware_iso8601(approved_at):
        raise ValueError("--approved-at must be a timezone-aware ISO-8601 timestamp")

    voice_preview = project_file(
        project, voice_preview_value, "--voice-preview"
    )
    voice_preview_report_path = project_file(
        project,
        voice_preview_report_value,
        "--voice-preview-report",
    )
    package_path = project_file(
        project, approval_package_value, "--approval-package"
    )
    validate_voice_preview(voice_preview)
    voice_preview_report = load_json(voice_preview_report_path)
    package = load_json(package_path)

    preview_report_errors = validate_voice_preview_report_document(
        voice_preview_report,
        case,
        file_sha256(voice_preview),
    )
    if preview_report_errors:
        raise ValueError("voice preview report mismatch: " + "; ".join(preview_report_errors))

    errors = validate_case(draft_validation_copy(case), require_approved=False)
    errors.extend(validate_caption_contract(case, manifest))
    errors.extend(validate_visual_source_contract(case, manifest))
    if errors:
        raise ValueError("current project is not approval-ready: " + "; ".join(errors))

    current_case_hash = file_sha256(case_path)
    current_manifest_hash = file_sha256(manifest_path)
    source_hashes = package.get("sourceHashes") or {}
    if str(source_hashes.get("caseSha256") or "") != current_case_hash:
        raise ValueError("approval package case source hash is stale")
    if str(source_hashes.get("renderManifestSha256") or "") != current_manifest_hash:
        raise ValueError("approval package render manifest source hash is stale")
    expected_package = build_package(project, case, manifest)
    if package != expected_package:
        raise ValueError(
            "approval package content does not match the deterministic current-source package"
        )

    receipt = {
        "version": 1,
        "contract": APPROVAL_RECEIPT_CONTRACT,
        "approvedBy": approved_by.strip(),
        "approvedAt": approved_at,
        "bindings": {
            "caseContentSha256": canonical_document_sha256(
                case_content_projection(case)
            ),
            "renderManifestSemanticSha256": canonical_document_sha256(
                render_manifest_semantic_projection(manifest)
            ),
            "voiceConfigSha256": canonical_document_sha256(
                voice_config_projection(case)
            ),
        },
        "voicePreview": {
            "path": voice_preview.relative_to(project).as_posix(),
            "sha256": file_sha256(voice_preview),
            "report": {
                "path": voice_preview_report_path.relative_to(project).as_posix(),
                "sha256": file_sha256(voice_preview_report_path),
            },
        },
        "approvalPackage": {
            "path": package_path.relative_to(project).as_posix(),
            "sha256": file_sha256(package_path),
            "sourceCaseSha256": current_case_hash,
            "sourceRenderManifestSha256": current_manifest_hash,
        },
    }
    approval = case.setdefault("approval", {})
    approval.update(
        {
            "contentApprovedByUser": True,
            "storyboardApprovedByUser": True,
            "paidGenerationAuthorized": True,
            "receipt": receipt,
        }
    )
    case["status"] = "approved-for-generation"
    receipt_errors = validate_approval_receipt(
        case, project=project, manifest=manifest
    )
    if receipt_errors:
        raise ValueError("generated approval receipt is invalid: " + "; ".join(receipt_errors))
    write_json_atomic(case_path, case)
    return {
        "ok": True,
        "status": case["status"],
        "case": str(case_path),
        "approvedBy": receipt["approvedBy"],
        "approvedAt": receipt["approvedAt"],
        "bindings": receipt["bindings"],
        "voicePreview": receipt["voicePreview"],
        "approvalPackage": receipt["approvalPackage"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument(
        "--approved-at",
        default="",
        help="timezone-aware ISO-8601 timestamp; defaults to the current UTC time",
    )
    parser.add_argument("--voice-preview", type=Path, required=True)
    parser.add_argument(
        "--voice-preview-report",
        type=Path,
        help="defaults to <voice-preview>.json, matching doubao_tts.py output",
    )
    parser.add_argument(
        "--approval-package", type=Path, default=Path("approval-package.json")
    )
    args = parser.parse_args()
    voice_preview_report = args.voice_preview_report or Path(
        str(args.voice_preview) + ".json"
    )
    approved_at = args.approved_at or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    try:
        result = record(
            args.project,
            approved_by=args.approved_by,
            approved_at=approved_at,
            voice_preview_value=args.voice_preview,
            voice_preview_report_value=voice_preview_report,
            approval_package_value=args.approval_package,
        )
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "errors": [str(exc)]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
