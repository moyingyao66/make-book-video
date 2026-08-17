#!/usr/bin/env python3
"""Validate the portable case and render manifest before paid generation or rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from build_timestamp_timeline import normalized_chars
from project_artifacts import (
    ProjectArtifactError,
    secure_project_file,
    secure_project_path as checked_project_path,
)


APPROVED_STATUSES = {"approved", "approved-for-generation", "ready"}
SCENE_TYPES = {"image", "video", "carousel", "solid"}
DEFAULT_NARRATIVE_PROFILE = "cognition-awakening-v1"
COPY_REVIEW_CHECKS = (
    "singleMainThesis",
    "audienceSituationConcrete",
    "bookEvidenceMapped",
    "examplesServeThesis",
    "endingReturnsToAudience",
    "readAloudNatural",
)
REQUIRED_DEFAULT_ROLES = (
    "fixed-opening",
    "book-reveal",
    "audience-problem",
    "alternative-explanation",
    "concrete-example",
    "practical-boundary",
    "audience-close",
)
CLAIM_CATEGORIES = {"fact", "attributed", "reader-reaction", "interpretation"}
CAPTION_MODES = {"bilingual", "zh-only"}
OPENING_VISUAL_SOURCES = {"pexels-video", "gpt-image"}
BODY_VISUAL_SOURCES = {"gpt-image", "pexels-video"}
BODY_VISUAL_ROLES = {
    "audience-problem",
    "alternative-explanation",
    "concrete-example",
    "practical-boundary",
    "audience-close",
}
APPROVAL_RECEIPT_CONTRACT = "make-book-video-approval-receipt-v1"
CASE_CONTENT_PROJECTION_FIELDS = (
    "version",
    "inputMode",
    "visualSourcePolicy",
    "narrativeProfile",
    "researchRoute",
    "book",
    "audience",
    "angle",
    "claims",
    "copyReview",
    "canvas",
    "segments",
    "timelineHolds",
)
MANIFEST_SCENE_SEMANTIC_FIELDS = (
    "type",
    "path",
    "items",
    "overlays",
    "fit",
    "motion",
    "zoomStep",
    "zoomLimit",
    "sourceProvider",
    "sourceRecord",
    "intent",
    "loop",
    "startSeconds",
    "itemFrames",
    "framesPerItem",
    "maxWidth",
    "maxHeight",
    "framePadding",
    "backgroundColor",
    "color",
)


def nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def non_whitespace_character_count(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def document_version(document: dict[str, Any]) -> int:
    try:
        return int(document.get("version") or 0)
    except (TypeError, ValueError):
        return 0


def canonical_document_sha256(document: Any) -> str:
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def case_content_projection(document: dict[str, Any]) -> dict[str, Any]:
    """Return approval-relevant case truth, excluding mutable approval state and voice."""
    return {
        field: document.get(field)
        for field in CASE_CONTENT_PROJECTION_FIELDS
        if field in document
    }


def render_manifest_semantic_projection(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Bind approved visual semantics without freezing later asset-review bookkeeping."""
    scenes: dict[str, Any] = {}
    for scene_id, raw_spec in sorted((manifest.get("sceneAssets") or {}).items()):
        spec = raw_spec if isinstance(raw_spec, dict) else {}
        scenes[str(scene_id)] = {
            field: spec.get(field)
            for field in MANIFEST_SCENE_SEMANTIC_FIELDS
            if field in spec
        }
    captions = manifest.get("captions") or {}
    return {
        "canvas": manifest.get("canvas") or {},
        "sceneAssets": scenes,
        "captions": {
            field: captions.get(field)
            for field in ("mode", "requireEnglish", "burnIn")
            if field in captions
        },
    }


def voice_config_projection(document: dict[str, Any]) -> dict[str, Any]:
    voice = document.get("voice") or {}
    return dict(voice) if isinstance(voice, dict) else {}


def is_sha256(value: Any) -> bool:
    candidate = str(value or "")
    if len(candidate) != 64:
        return False
    try:
        int(candidate, 16)
    except ValueError:
        return False
    return candidate == candidate.lower()


def is_timezone_aware_iso8601(value: Any) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def approval_receipt_required(
    document: dict[str, Any], require_approved: bool
) -> bool:
    return document_version(document) >= 3 and (
        require_approved or document.get("status") in APPROVED_STATUSES
    )


def narrative_profile_id(document: dict[str, Any]) -> str:
    profile = document.get("narrativeProfile")
    return str(profile.get("id") or "").strip() if isinstance(profile, dict) else ""


def validate_voice_preview_report_document(
    report: dict[str, Any],
    document: dict[str, Any],
    audio_sha256: str,
) -> list[str]:
    errors: list[str] = []
    raw_voice = document.get("voice")
    voice = raw_voice if isinstance(raw_voice, dict) else {}
    if str(report.get("audioSha256") or "") != audio_sha256:
        errors.append("approval voice preview report audioSha256 differs from the WAV")
    for field in ("resourceId", "speaker"):
        if str(report.get(field) or "") != str(voice.get(field) or ""):
            errors.append(
                f"approval voice preview report {field} differs from case.voice"
            )
    try:
        report_rate = int(report.get("speechRate"))
        voice_rate = int(voice.get("speechRate"))
    except (TypeError, ValueError):
        errors.append(
            "approval voice preview report speechRate or case.voice.speechRate is invalid"
        )
    else:
        if report_rate != voice_rate:
            errors.append(
                "approval voice preview report speechRate differs from case.voice"
            )
    if report.get("enableSubtitle") is not voice.get("enableSubtitle"):
        errors.append(
            "approval voice preview report enableSubtitle differs from case.voice"
        )
    return errors


def validate_approval_receipt(
    document: dict[str, Any],
    *,
    project: Path | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    raw_approval = document.get("approval")
    approval = raw_approval if isinstance(raw_approval, dict) else {}
    receipt = approval.get("receipt")
    if not isinstance(receipt, dict):
        return ["approval.receipt is required for approved version 3 projects"]
    if receipt.get("version") != 1:
        errors.append("approval.receipt.version must be 1")
    if str(receipt.get("contract") or "") != APPROVAL_RECEIPT_CONTRACT:
        errors.append(
            f"approval.receipt.contract must be {APPROVAL_RECEIPT_CONTRACT}"
        )
    if not nonempty(receipt.get("approvedBy")):
        errors.append("approval.receipt.approvedBy is required")
    if not is_timezone_aware_iso8601(receipt.get("approvedAt")):
        errors.append("approval.receipt.approvedAt must be a timezone-aware ISO-8601 timestamp")

    bindings = receipt.get("bindings") or {}
    expected_case_hash = canonical_document_sha256(case_content_projection(document))
    if str(bindings.get("caseContentSha256") or "") != expected_case_hash:
        errors.append("approval receipt case content projection is stale")
    expected_voice_hash = canonical_document_sha256(voice_config_projection(document))
    if str(bindings.get("voiceConfigSha256") or "") != expected_voice_hash:
        errors.append("approval receipt voice configuration is stale")
    manifest_hash = str(bindings.get("renderManifestSemanticSha256") or "")
    if not is_sha256(manifest_hash):
        errors.append(
            "approval.receipt.bindings.renderManifestSemanticSha256 is required"
        )
    elif manifest is not None:
        expected_manifest_hash = canonical_document_sha256(
            render_manifest_semantic_projection(manifest)
        )
        if manifest_hash != expected_manifest_hash:
            errors.append("approval receipt render manifest semantic projection is stale")

    preview = receipt.get("voicePreview") or {}
    preview_path_value = preview.get("path")
    preview_hash = str(preview.get("sha256") or "")
    if not nonempty(preview_path_value):
        errors.append("approval.receipt.voicePreview.path is required")
    if not is_sha256(preview_hash):
        errors.append("approval.receipt.voicePreview.sha256 is required")
    preview_report = preview.get("report") or {}
    preview_report_path_value = preview_report.get("path")
    preview_report_hash = str(preview_report.get("sha256") or "")
    if not nonempty(preview_report_path_value):
        errors.append("approval.receipt.voicePreview.report.path is required")
    if not is_sha256(preview_report_hash):
        errors.append("approval.receipt.voicePreview.report.sha256 is required")

    package = receipt.get("approvalPackage") or {}
    package_path_value = package.get("path")
    package_hash = str(package.get("sha256") or "")
    if not nonempty(package_path_value):
        errors.append("approval.receipt.approvalPackage.path is required")
    if not is_sha256(package_hash):
        errors.append("approval.receipt.approvalPackage.sha256 is required")
    for field in ("sourceCaseSha256", "sourceRenderManifestSha256"):
        if not is_sha256(package.get(field)):
            errors.append(f"approval.receipt.approvalPackage.{field} is required")

    if project is None:
        return errors

    actual_preview_hash = ""
    preview_path = (
        safe_project_path(
            project,
            preview_path_value,
            "approval voice preview",
            errors,
        )
        if nonempty(preview_path_value)
        else None
    )
    if preview_path is not None:
        if preview_path.suffix.lower() != ".wav":
            errors.append("approval voice preview must be a WAV file")
        elif not preview_path.is_file():
            errors.append(f"approval voice preview does not exist: {preview_path}")
        else:
            actual_preview_hash = file_sha256(preview_path)
            if is_sha256(preview_hash) and actual_preview_hash != preview_hash:
                errors.append("approval voice preview hash is stale")

    preview_report_path = (
        safe_project_path(
            project,
            preview_report_path_value,
            "approval voice preview report",
            errors,
        )
        if nonempty(preview_report_path_value)
        else None
    )
    if preview_report_path is not None:
        if not preview_report_path.is_file():
            errors.append(
                f"approval voice preview report does not exist: {preview_report_path}"
            )
        else:
            if (
                is_sha256(preview_report_hash)
                and file_sha256(preview_report_path) != preview_report_hash
            ):
                errors.append("approval voice preview report hash is stale")
            try:
                preview_report_document = json.loads(
                    preview_report_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"approval voice preview report is invalid JSON: {exc}")
            else:
                if not isinstance(preview_report_document, dict):
                    errors.append("approval voice preview report root must be an object")
                else:
                    errors.extend(
                        validate_voice_preview_report_document(
                            preview_report_document,
                            document,
                            actual_preview_hash or preview_hash,
                        )
                    )

    package_path = (
        safe_project_path(
            project,
            package_path_value,
            "approval package",
            errors,
        )
        if nonempty(package_path_value)
        else None
    )
    if package_path is not None:
        if not package_path.is_file():
            errors.append(f"approval package does not exist: {package_path}")
        else:
            if is_sha256(package_hash) and file_sha256(package_path) != package_hash:
                errors.append("approval package hash is stale")
            try:
                package_document = json.loads(package_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"approval package is invalid JSON: {exc}")
            else:
                if package_document.get("contract") != "make-book-video-approval-v1":
                    errors.append("approval package has an unsupported contract")
                source_hashes = package_document.get("sourceHashes") or {}
                if str(source_hashes.get("caseSha256") or "") != str(
                    package.get("sourceCaseSha256") or ""
                ):
                    errors.append("approval package source case hash differs from receipt")
                if str(source_hashes.get("renderManifestSha256") or "") != str(
                    package.get("sourceRenderManifestSha256") or ""
                ):
                    errors.append(
                        "approval package source render manifest hash differs from receipt"
                    )
    return errors


def visual_policy_required(document: dict[str, Any]) -> bool:
    try:
        version_requires_it = int(document.get("version") or 0) >= 3
    except (TypeError, ValueError):
        version_requires_it = False
    return version_requires_it or "visualSourcePolicy" in document


def validate_visual_source_policy(document: dict[str, Any]) -> list[str]:
    if not visual_policy_required(document):
        return []
    errors: list[str] = []
    policy = document.get("visualSourcePolicy")
    if not isinstance(policy, dict):
        return ["visualSourcePolicy is required for version 3 projects"]
    if policy.get("selectionStatus") != "confirmed":
        errors.append("visualSourcePolicy.selectionStatus must be confirmed")
    if policy.get("selectionMethod") != "host-structured-choice":
        errors.append(
            "visualSourcePolicy.selectionMethod must record host-structured-choice"
        )
    if policy.get("selectedAtProjectStart") is not True:
        errors.append("visualSourcePolicy.selectedAtProjectStart must be true")
    opening_source = str(policy.get("openingSource") or "")
    body_source = str(policy.get("bodySource") or "")
    if opening_source not in OPENING_VISUAL_SOURCES:
        errors.append(
            "visualSourcePolicy.openingSource must be pexels-video or gpt-image"
        )
    if body_source not in BODY_VISUAL_SOURCES:
        errors.append(
            "visualSourcePolicy.bodySource must be gpt-image or pexels-video"
        )
    if policy.get("silentFallbackAllowed") is not False:
        errors.append("visualSourcePolicy.silentFallbackAllowed must be false")
    return errors


def validate_declared_research_fallback(document: dict[str, Any]) -> list[str]:
    """Reject a claimed fallback route until every source is attributable."""
    route = document.get("researchRoute")
    if not isinstance(route, dict):
        return []
    if str(route.get("status") or "") != "unavailable-with-fallback":
        return []
    errors: list[str] = []
    fallback_items = route.get("fallbacks")
    if not isinstance(fallback_items, list) or not fallback_items:
        return [
            "researchRoute.fallbacks must document at least one attributable fallback"
        ]
    for index, fallback in enumerate(fallback_items, start=1):
        if not isinstance(fallback, dict):
            errors.append(f"researchRoute.fallbacks[{index}] must be an object")
            continue
        source_url = fallback.get("sourceUrl")
        reason = fallback.get("reason")
        if not isinstance(source_url, str) or not source_url.strip():
            errors.append(f"researchRoute.fallbacks[{index}].sourceUrl is required")
        else:
            parsed_source_url = urlparse(source_url.strip())
            if (
                parsed_source_url.scheme not in {"http", "https"}
                or not parsed_source_url.netloc
            ):
                errors.append(
                    f"researchRoute.fallbacks[{index}].sourceUrl must be an attributable HTTP(S) URL"
                )
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"researchRoute.fallbacks[{index}].reason is required")
    return errors


def validate_narrative_evidence(
    document: dict[str, Any], profile_id: str
) -> list[str]:
    """Validate source and editorial evidence for every narrative profile.

    Custom structure changes the order of the copy; it must not bypass the
    source, claim-mapping, or copy-review gates shared by the default profile.
    """
    errors: list[str] = []
    input_mode = str(document.get("inputMode") or "")
    if input_mode in {"book-title", "book-page"}:
        input_label = input_mode
        route = document.get("researchRoute") or {}
        if str(route.get("primary") or "") != "weread-skills":
            errors.append(
                f"{input_label} input requires weread-skills as researchRoute.primary"
            )
        route_status = str(route.get("status") or "")
        if route_status not in {"captured", "unavailable-with-fallback"}:
            errors.append(
                f"{input_label} input requires captured WeRead research or a documented "
                "unavailable-with-fallback route before copy approval"
            )
        if not nonempty(route.get("skillVersion")):
            errors.append("researchRoute.skillVersion is required")
        if route_status == "captured":
            if not nonempty(route.get("bookId")):
                errors.append("researchRoute.bookId is required for captured WeRead research")
            if len(route.get("capturedInputs") or []) < 3:
                errors.append(
                    "researchRoute.capturedInputs must record the captured WeRead inputs"
                )
        if route.get("privateNotesUsed") not in {True, False}:
            errors.append("researchRoute.privateNotesUsed must be boolean")

    claims = document.get("claims") or []
    claim_ids: set[str] = set()
    if not claims:
        errors.append(f"{profile_id} requires source-checked claims")
    for index, claim in enumerate(claims, start=1):
        claim_id = str((claim or {}).get("id") or "").strip()
        if not claim_id:
            errors.append(f"claim {index} has no id")
        elif claim_id in claim_ids:
            errors.append(f"duplicate claim id: {claim_id}")
        else:
            claim_ids.add(claim_id)
        category = str((claim or {}).get("category") or "")
        if category not in CLAIM_CATEGORIES:
            errors.append(f"claim {claim_id or index} has unsupported category: {category}")
        if not nonempty((claim or {}).get("text")):
            errors.append(f"claim {claim_id or index} has no text")
        if not nonempty((claim or {}).get("sourceUrl")):
            errors.append(f"claim {claim_id or index} has no sourceUrl")

    non_evidentiary_roles = {
        "fixed-opening",
        "book-reveal",
        "audience-problem",
        "audience-close",
        "hook",
        "transition",
        "cta",
        "closing",
    }
    for segment in document.get("segments") or []:
        segment_id = str(segment.get("id") or "")
        source_ids = [str(value) for value in (segment.get("sourceClaimIds") or [])]
        unknown = [value for value in source_ids if value not in claim_ids]
        if unknown:
            errors.append(f"segment {segment_id} references unknown claim ids: {', '.join(unknown)}")
        role = str(segment.get("role") or "")
        if role not in non_evidentiary_roles and not source_ids:
            errors.append(f"segment {segment_id} must map its substantial content to claims")

    review = document.get("copyReview") or {}
    if str(review.get("status") or "") != "completed":
        errors.append("copyReview.status must be completed before approval")
    if not nonempty(review.get("reviewedBy")):
        errors.append("copyReview.reviewedBy is required")
    review_checks = review.get("checks") or {}
    for check in COPY_REVIEW_CHECKS:
        if review_checks.get(check) is not True:
            errors.append(f"copyReview.checks.{check} must be true")

    return errors


def validate_visual_source_contract(
    case: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    if not visual_policy_required(case):
        return []
    policy = case.get("visualSourcePolicy") or {}
    opening_source = str(policy.get("openingSource") or "")
    body_source = str(policy.get("bodySource") or "")
    if (
        opening_source not in OPENING_VISUAL_SOURCES
        or body_source not in BODY_VISUAL_SOURCES
    ):
        return []  # The case-level policy validator reports the malformed choice.

    errors: list[str] = []
    scene_assets = manifest.get("sceneAssets") or {}
    for segment in case.get("segments") or []:
        scene_id = str(segment.get("id") or "")
        role = str(segment.get("role") or "")
        if role == "fixed-opening":
            source = opening_source
        elif role in BODY_VISUAL_ROLES:
            source = body_source
        else:
            continue
        spec = scene_assets.get(scene_id)
        if not isinstance(spec, dict):
            continue  # The general manifest validator reports a missing scene.
        if source == "pexels-video":
            expected_type = "video"
            expected_provider = "pexels"
            expected_path = f"assets/pexels/{scene_id}.mp4"
            expected_record = f"assets/pexels/{scene_id}-source.json"
        else:
            expected_type = "image"
            expected_provider = "gpt-image"
            expected_path = f"visuals/{scene_id}.png"
            expected_record = ""
        if str(spec.get("type") or "") != expected_type:
            errors.append(
                f"scene {scene_id} must use type {expected_type} for selected {source}"
            )
        if str(spec.get("sourceProvider") or "") != expected_provider:
            errors.append(
                f"scene {scene_id} must use sourceProvider {expected_provider}"
            )
        if str(spec.get("path") or "") != expected_path:
            errors.append(
                f"scene {scene_id} path must match selected source: {expected_path}"
            )
        if str(segment.get("asset") or "") != expected_path:
            errors.append(
                f"case segment {scene_id} asset must match selected source: {expected_path}"
            )
        if expected_record and str(spec.get("sourceRecord") or "") != expected_record:
            errors.append(
                f"scene {scene_id} sourceRecord must be {expected_record}"
            )
        if not expected_record and nonempty(spec.get("sourceRecord")):
            errors.append(
                f"scene {scene_id} must not retain a Pexels sourceRecord on GPT image route"
            )
    return errors


def validate_narrative_contract(
    document: dict[str, Any], require_approved: bool
) -> list[str]:
    errors: list[str] = []
    raw_profile = document.get("narrativeProfile")
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    profile_id = narrative_profile_id(document)
    if not profile_id:
        if document_version(document) >= 3:
            errors.append("version 3 projects require narrativeProfile.id")
        return errors  # Legacy cases remain readable; new projects declare a profile.
    if profile_id in {"custom", "preserve-approved-script"}:
        return validate_narrative_evidence(document, profile_id)
    if profile_id != DEFAULT_NARRATIVE_PROFILE:
        return [f"unsupported narrativeProfile.id: {profile_id}"]

    segments = document.get("segments") or []
    segment_by_id = {
        str(segment.get("id") or ""): segment
        for segment in segments
        if nonempty(segment.get("id"))
    }
    role_to_segments: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        role_to_segments.setdefault(str(segment.get("role") or ""), []).append(segment)

    intro_id = str(profile.get("introSegmentId") or "intro")
    reveal_id = str(profile.get("bookRevealSegmentId") or "book-reveal")
    carousel_id = str(profile.get("carouselHoldId") or "anticipation-carousel")
    fixed_opening = str(profile.get("fixedOpening") or "今天分享的是。").strip()
    if not segments or str(segments[0].get("id") or "") != intro_id:
        errors.append(f"{profile_id} requires {intro_id} as the first narrated segment")
    intro = segment_by_id.get(intro_id) or {}
    if str(intro.get("narration") or "").strip() != fixed_opening:
        errors.append(f"segment {intro_id} must say exactly: {fixed_opening}")
    if len(segments) < 2 or str(segments[1].get("id") or "") != reveal_id:
        errors.append(f"{profile_id} requires {reveal_id} immediately after the carousel")

    holds = document.get("timelineHolds") or []
    carousel = next(
        (hold for hold in holds if str(hold.get("id") or "") == carousel_id), None
    )
    if not carousel:
        errors.append(f"{profile_id} requires timeline hold {carousel_id}")
    else:
        if str(carousel.get("afterSegmentId") or "") != intro_id:
            errors.append(f"timeline hold {carousel_id} must follow {intro_id}")
        try:
            expected_frames = int(profile.get("carouselFrames") or 45)
            actual_frames = int(carousel.get("durationFrames") or 0)
            if expected_frames <= 0:
                raise ValueError
            if actual_frames != expected_frames:
                errors.append(
                    f"timeline hold {carousel_id} must use the declared {expected_frames} frames"
                )
        except (TypeError, ValueError):
            errors.append("narrativeProfile.carouselFrames must be a positive integer")

    reveal = segment_by_id.get(reveal_id) or {}
    reveal_text = str(reveal.get("narration") or "")
    book = document.get("book") or {}
    title = str(book.get("title") or "").strip()
    if title and title not in reveal_text:
        errors.append(f"segment {reveal_id} must contain the exact book title")
    authors = [str(author).strip() for author in (book.get("authors") or []) if str(author).strip()]
    if authors and authors[0] not in reveal_text:
        errors.append(f"segment {reveal_id} must contain the primary author")

    for role in REQUIRED_DEFAULT_ROLES:
        if len(role_to_segments.get(role) or []) != 1:
            errors.append(f"{profile_id} requires exactly one segment with role {role}")
    for role in ("audience-problem", "audience-close"):
        matches = role_to_segments.get(role) or []
        if matches and "你" not in str(matches[0].get("narration") or ""):
            errors.append(f"role {role} must address the viewer directly with 你")

    target = profile.get("targetCharacters") or {}
    try:
        minimum = int(target.get("min"))
        maximum = int(target.get("max"))
        if minimum <= 0 or maximum < minimum:
            raise ValueError
        narration_text = "".join(str(item.get("narration") or "") for item in segments)
        character_count = non_whitespace_character_count(narration_text)
        if not minimum <= character_count <= maximum:
            errors.append(
                f"narration has {character_count} non-whitespace characters; "
                f"declared range is {minimum}-{maximum}"
            )
    except (TypeError, ValueError):
        errors.append("narrativeProfile.targetCharacters needs positive integer min/max")

    errors.extend(validate_narrative_evidence(document, profile_id))
    return errors


def validate_case(
    document: dict[str, Any],
    require_approved: bool,
    *,
    project: Path | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if require_approved and document.get("status") not in APPROVED_STATUSES:
        errors.append("case.status must record content approval before paid generation")
    profile_id = narrative_profile_id(document)
    receipt_required = approval_receipt_required(document, require_approved)
    if (require_approved and profile_id) or receipt_required:
        raw_approval = document.get("approval")
        approval = raw_approval if isinstance(raw_approval, dict) else {}
        for field in (
            "contentApprovedByUser",
            "storyboardApprovedByUser",
            "paidGenerationAuthorized",
        ):
            if approval.get(field) is not True:
                errors.append(f"approval.{field} must be true before paid generation")
    if receipt_required:
        errors.extend(
            validate_approval_receipt(
                document,
                project=project,
                manifest=manifest,
            )
        )
    book = document.get("book") or {}
    if not nonempty(book.get("title")):
        errors.append("book.title is required")
    errors.extend(validate_visual_source_policy(document))
    errors.extend(validate_declared_research_fallback(document))

    canvas = document.get("canvas") or {}
    for field in ("width", "height", "fps"):
        try:
            if int(canvas.get(field) or 0) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"canvas.{field} must be a positive integer")

    voice = document.get("voice") or {}
    if not nonempty(voice.get("resourceId")):
        errors.append("voice.resourceId is required")
    if not nonempty(voice.get("speaker")):
        errors.append("voice.speaker is required")
    try:
        rate = int(voice.get("speechRate"))
        if not -50 <= rate <= 100:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("voice.speechRate must be an integer between -50 and 100")
    if voice.get("enableSubtitle") is not True:
        errors.append("voice.enableSubtitle must be true")
    if voice.get("requireSingleProviderRequest") is not True:
        errors.append("voice.requireSingleProviderRequest must be true")

    segments = document.get("segments") or []
    if not segments:
        errors.append("at least one narrated segment is required")
        return errors
    segment_ids: set[str] = set()
    caption_ids: set[str] = set()
    for index, segment in enumerate(segments, start=1):
        segment_id = str(segment.get("id") or "").strip()
        if not segment_id:
            errors.append(f"segment {index} has no id")
            continue
        if segment_id in segment_ids:
            errors.append(f"duplicate segment id: {segment_id}")
        segment_ids.add(segment_id)
        narration = str(segment.get("narration") or "").strip()
        if not normalized_chars(narration):
            errors.append(f"segment {segment_id} has no alignable narration")
        captions = segment.get("captions") or []
        if not captions:
            errors.append(f"segment {segment_id} has no caption cards")
            continue
        caption_text = ""
        for card_index, card in enumerate(captions, start=1):
            card_id = str(card.get("id") or "").strip()
            if not card_id:
                errors.append(f"segment {segment_id} caption {card_index} has no id")
            elif card_id in caption_ids:
                errors.append(f"duplicate caption id: {card_id}")
            else:
                caption_ids.add(card_id)
            caption_text += str(card.get("zhText") or card.get("text") or "")
        if normalized_chars(caption_text) != normalized_chars(narration):
            errors.append(
                f"caption cards for segment {segment_id} do not exactly cover narration"
            )

    hold_ids: set[str] = set()
    for index, hold in enumerate(document.get("timelineHolds") or [], start=1):
        hold_id = str(hold.get("id") or "").strip()
        if not hold_id:
            errors.append(f"timeline hold {index} has no id")
        elif hold_id in hold_ids or hold_id in segment_ids:
            errors.append(f"duplicate scene or hold id: {hold_id}")
        else:
            hold_ids.add(hold_id)
        if str(hold.get("afterSegmentId") or "") not in segment_ids:
            errors.append(f"timeline hold {hold_id or index} references an unknown segment")
        try:
            if int(hold.get("durationFrames") or 0) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"timeline hold {hold_id or index} needs positive durationFrames")
    errors.extend(validate_narrative_contract(document, require_approved))
    return errors


def validate_caption_contract(
    case: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    captions = manifest.get("captions") or {}
    mode = str(captions.get("mode") or "").strip().lower()
    if mode not in CAPTION_MODES:
        return ["captions.mode must be bilingual or zh-only"]

    if mode == "bilingual":
        if captions.get("requireEnglish") is not True:
            errors.append("bilingual captions require captions.requireEnglish=true")
        for segment in case.get("segments") or []:
            for card in segment.get("captions") or []:
                if not nonempty(card.get("enText")):
                    errors.append(
                        f"bilingual caption {card.get('id') or 'unknown'} has empty enText"
                    )

    canvas = manifest.get("canvas") or case.get("canvas") or {}
    height = int(canvas.get("height") or 0)
    try:
        chinese_size = int(captions.get("fontSize") or 0)
        if chinese_size < 64:
            errors.append("captions.fontSize must be at least 64 for 1080x1920 delivery")
    except (TypeError, ValueError):
        errors.append("captions.fontSize must be an integer")
    try:
        english_size = int(captions.get("englishFontSize") or 0)
        if mode == "bilingual" and english_size < 36:
            errors.append(
                "captions.englishFontSize must be at least 36 for bilingual delivery"
            )
    except (TypeError, ValueError):
        errors.append("captions.englishFontSize must be an integer")
    try:
        position_y = int(captions.get("positionY"))
        safe_bottom = int(captions.get("safeBottomPx"))
        if safe_bottom < 300:
            errors.append("captions.safeBottomPx must reserve at least 300 pixels")
        if height <= 0 or position_y > height - safe_bottom:
            errors.append("captions.positionY intrudes into the reserved bottom safe zone")
    except (TypeError, ValueError):
        errors.append("captions.positionY and safeBottomPx must be integers")
    return errors


def safe_project_path(project: Path, value: Any, label: str, errors: list[str]) -> Path | None:
    try:
        return checked_project_path(project, value, label)
    except ProjectArtifactError as exc:
        errors.append(str(exc))
        return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_pexels_source_record(
    project: Path,
    scene_id: str,
    spec: dict[str, Any],
    check_assets: bool,
) -> list[str]:
    errors: list[str] = []
    record_path = safe_project_path(
        project,
        spec.get("sourceRecord"),
        f"scene {scene_id} Pexels sourceRecord",
        errors,
    )
    if record_path is None:
        return errors
    if not record_path.is_file():
        if check_assets:
            errors.append(f"scene {scene_id} Pexels sourceRecord does not exist: {record_path}")
        return errors
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"scene {scene_id} Pexels sourceRecord is invalid JSON: {exc}"]
    if record.get("provider") != "Pexels":
        errors.append(f"scene {scene_id} Pexels sourceRecord has wrong provider")
    if str(record.get("sceneId") or "") != scene_id:
        errors.append(f"scene {scene_id} Pexels sourceRecord has wrong sceneId")
    for field in ("query", "pexelsPage"):
        if not nonempty(record.get(field)):
            errors.append(f"scene {scene_id} Pexels sourceRecord.{field} is required")
    creator = record.get("creator") or {}
    for field in ("name", "url"):
        if not nonempty(creator.get(field)):
            errors.append(
                f"scene {scene_id} Pexels sourceRecord.creator.{field} is required"
            )
    selected = record.get("selectedFile") or {}
    if not nonempty(selected.get("url")):
        errors.append(f"scene {scene_id} Pexels selectedFile.url is required")
    for field in ("width", "height"):
        try:
            if int(selected.get(field) or 0) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(
                f"scene {scene_id} Pexels selectedFile.{field} must be positive"
            )
    attribution = record.get("attribution") or {}
    for field in ("linkBack", "text"):
        if not nonempty(attribution.get(field)):
            errors.append(
                f"scene {scene_id} Pexels sourceRecord.attribution.{field} is required"
            )
    downloaded = record.get("downloadedFile") or {}
    if str(downloaded.get("path") or "") != str(spec.get("path") or ""):
        errors.append(
            f"scene {scene_id} Pexels downloadedFile.path must match manifest path"
        )
    recorded_hash = str(downloaded.get("sha256") or "")
    if len(recorded_hash) != 64:
        errors.append(f"scene {scene_id} Pexels downloadedFile.sha256 is required")
    review = record.get("frameReview") or {}
    if review.get("status") != "passed":
        errors.append(f"scene {scene_id} Pexels frameReview.status must be passed")
    if not nonempty(review.get("reviewedAt")):
        errors.append(f"scene {scene_id} Pexels frameReview.reviewedAt is required")
    if len(review.get("positions") or []) < 3:
        errors.append(
            f"scene {scene_id} Pexels frameReview.positions needs at least three checks"
        )
    video_path = safe_project_path(
        project, spec.get("path"), f"scene {scene_id} Pexels video", errors
    )
    if (
        check_assets
        and video_path
        and video_path.is_file()
        and len(recorded_hash) == 64
        and file_sha256(video_path) != recorded_hash
    ):
        errors.append(f"scene {scene_id} Pexels downloaded file hash is stale")
    return errors


def validate_manifest(
    project: Path,
    case: dict[str, Any],
    manifest: dict[str, Any],
    check_assets: bool,
) -> list[str]:
    errors: list[str] = []
    if approval_receipt_required(case, require_approved=False):
        errors.extend(
            validate_approval_receipt(case, project=project, manifest=manifest)
        )
    errors.extend(validate_caption_contract(case, manifest))
    errors.extend(validate_visual_source_contract(case, manifest))
    canvas = manifest.get("canvas") or {}
    if canvas != (case.get("canvas") or {}):
        errors.append("render manifest canvas must exactly match case.canvas")
    scene_assets = manifest.get("sceneAssets") or {}
    required_ids = [str(item.get("id") or "") for item in case.get("segments") or []]
    required_ids += [
        str(item.get("id") or "")
        for item in case.get("timelineHolds") or []
        if int(item.get("durationFrames") or 0) > 0
    ]
    for scene_id in required_ids:
        spec = scene_assets.get(scene_id)
        if not isinstance(spec, dict):
            errors.append(f"render manifest is missing sceneAssets.{scene_id}")
            continue
        scene_type = str(spec.get("type") or "")
        if scene_type not in SCENE_TYPES:
            errors.append(f"scene {scene_id} has unsupported type: {scene_type}")
            continue
        if not nonempty(spec.get("intent")):
            errors.append(f"scene {scene_id} must declare its visual intent")
        asset_status = str(spec.get("assetStatus") or "").strip()
        if not asset_status:
            errors.append(f"scene {scene_id} must record asset review status")
        elif check_assets and asset_status.lower().startswith("pending"):
            errors.append(
                f"scene {scene_id} assetStatus must be reviewed before render; "
                f"got {asset_status}"
            )
        paths: list[Any] = []
        if scene_type in {"image", "video"}:
            paths.append(spec.get("path"))
            for overlay in spec.get("overlays") or []:
                paths.append((overlay or {}).get("path"))
        elif scene_type == "carousel":
            paths.extend(spec.get("items") or [])
            if len(paths) < 2:
                errors.append(f"carousel scene {scene_id} needs at least two items")
        for item_index, value in enumerate(paths, start=1):
            path = safe_project_path(
                project, value, f"scene {scene_id} asset {item_index}", errors
            )
            if check_assets and path and not path.is_file():
                errors.append(f"scene {scene_id} asset does not exist: {path}")
        if str(spec.get("sourceProvider") or "") == "pexels":
            errors.extend(
                validate_pexels_source_record(project, scene_id, spec, check_assets)
            )

    audio = manifest.get("audio") or {}
    for label, value in (
        ("audio.narration", audio.get("narration")),
        ("captions.ass", (manifest.get("captions") or {}).get("ass")),
    ):
        path = safe_project_path(project, value, label, errors)
        if check_assets and path and not path.is_file():
            errors.append(f"required render input does not exist: {path}")
    bgm = audio.get("bgm") or {}
    if nonempty(bgm.get("path")):
        path = safe_project_path(project, bgm.get("path"), "audio.bgm", errors)
        if check_assets and path and not path.is_file():
            errors.append(f"BGM does not exist: {path}")
    for index, sfx in enumerate(audio.get("sfx") or [], start=1):
        path = safe_project_path(project, (sfx or {}).get("path"), f"audio.sfx {index}", errors)
        if check_assets and path and not path.is_file():
            errors.append(f"SFX does not exist: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--stage", choices=("draft", "synthesis", "render"), default="draft")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        case_path = secure_project_file(project, "case.json", "case.json")
    except ProjectArtifactError as exc:
        raise SystemExit(f"Invalid case file: {exc}") from exc
    case = json.loads(case_path.read_text(encoding="utf-8"))
    try:
        manifest_path = secure_project_file(
            project, "render-manifest.json", "render-manifest.json"
        )
    except ProjectArtifactError as exc:
        manifest_path = project / "render-manifest.json"
        manifest_error = f"invalid render manifest: {exc}"
        manifest = None
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_error = ""
    errors = validate_case(
        case,
        require_approved=args.stage in {"synthesis", "render"},
        project=project,
        manifest=manifest,
    )
    if manifest_error:
        errors.append(manifest_error)
    elif manifest is not None:
        if args.stage == "render":
            errors.extend(validate_manifest(project, case, manifest, check_assets=True))
        else:
            errors.extend(validate_caption_contract(case, manifest))
            errors.extend(validate_visual_source_contract(case, manifest))
    errors = list(dict.fromkeys(errors))
    report = {"ok": not errors, "stage": args.stage, "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
