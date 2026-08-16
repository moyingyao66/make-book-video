#!/usr/bin/env python3
"""Validate the portable case and render manifest before paid generation or rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_timestamp_timeline import normalized_chars


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


def nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def non_whitespace_character_count(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def validate_narrative_contract(
    document: dict[str, Any], require_approved: bool
) -> list[str]:
    errors: list[str] = []
    profile = document.get("narrativeProfile") or {}
    profile_id = str(profile.get("id") or "").strip()
    if not profile_id:
        return errors  # Legacy cases remain readable; new projects declare a profile.
    if require_approved:
        approval = document.get("approval") or {}
        for field in (
            "contentApprovedByUser",
            "storyboardApprovedByUser",
            "paidGenerationAuthorized",
        ):
            if approval.get(field) is not True:
                errors.append(f"approval.{field} must be true before paid generation")
    if profile_id in {"custom", "preserve-approved-script"}:
        return errors
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

    input_mode = str(document.get("inputMode") or "")
    if input_mode == "book-title":
        route = document.get("researchRoute") or {}
        if str(route.get("primary") or "") != "weread-skills":
            errors.append("book-title input requires weread-skills as researchRoute.primary")
        if str(route.get("status") or "") != "captured":
            errors.append("book-title input requires captured WeRead research before copy approval")
        if not nonempty(route.get("skillVersion")):
            errors.append("researchRoute.skillVersion is required")
        if not nonempty(route.get("bookId")):
            errors.append("researchRoute.bookId is required")
        if len(route.get("capturedInputs") or []) < 3:
            errors.append("researchRoute.capturedInputs must record the captured WeRead inputs")
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

    for segment in segments:
        segment_id = str(segment.get("id") or "")
        source_ids = [str(value) for value in (segment.get("sourceClaimIds") or [])]
        unknown = [value for value in source_ids if value not in claim_ids]
        if unknown:
            errors.append(f"segment {segment_id} references unknown claim ids: {', '.join(unknown)}")
        if str(segment.get("role") or "") in {
            "alternative-explanation",
            "concrete-example",
            "practical-boundary",
        } and not source_ids:
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


def validate_case(document: dict[str, Any], require_approved: bool) -> list[str]:
    errors: list[str] = []
    if require_approved and document.get("status") not in APPROVED_STATUSES:
        errors.append("case.status must record content approval before paid generation")
    book = document.get("book") or {}
    if not nonempty(book.get("title")):
        errors.append("book.title is required")

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
    path = Path(str(value or ""))
    if not str(path):
        errors.append(f"{label} path is empty")
        return None
    if path.is_absolute():
        errors.append(f"{label} must use a project-relative path")
        return None
    resolved = (project / path).resolve()
    try:
        resolved.relative_to(project)
    except ValueError:
        errors.append(f"{label} escapes the project directory")
        return None
    return resolved


def validate_manifest(
    project: Path,
    case: dict[str, Any],
    manifest: dict[str, Any],
    check_assets: bool,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_caption_contract(case, manifest))
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
        if not nonempty(spec.get("assetStatus")):
            errors.append(f"scene {scene_id} must record asset review status")
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
    case_path = project / "case.json"
    if not case_path.is_file():
        raise SystemExit(f"Missing case file: {case_path}")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    errors = validate_case(case, require_approved=args.stage in {"synthesis", "render"})
    manifest_path = project / "render-manifest.json"
    if not manifest_path.is_file():
        errors.append(f"missing render manifest: {manifest_path}")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if args.stage == "render":
            errors.extend(validate_manifest(project, case, manifest, check_assets=True))
        else:
            errors.extend(validate_caption_contract(case, manifest))
    report = {"ok": not errors, "stage": args.stage, "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
