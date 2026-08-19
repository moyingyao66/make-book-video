#!/usr/bin/env python3
"""Score objective make-book-video project gates at a declared workflow stage."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from build_approval_package import build_package
from build_editor_plan import build_editor_plan
from qa_video import provider_timing_report
from validate_case import (
    file_sha256,
    validate_approval_receipt,
    validate_caption_contract,
    validate_case,
    validate_manifest,
    validate_visual_source_contract,
    validate_visual_source_policy,
)
from validate_editable_delivery import validate as validate_editable_delivery
from verify_delivery import validate_delivery


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = SKILL_DIR / "evals/skill-evals.json"
STAGE_ORDER = {"draft": 0, "synthesis": 1, "render": 2, "delivery": 3}


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing JSON file: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return document


def gate(gate_id: str, check: Callable[[], list[str]]) -> dict[str, Any]:
    try:
        errors = check()
    except (
        SystemExit,
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as exc:
        errors = [str(exc)]
    return {"id": gate_id, "passed": not errors, "errors": errors}


def approval_output_errors(
    project: Path, case: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    approval = case.get("approval") if isinstance(case.get("approval"), dict) else {}
    receipt = approval.get("receipt") if isinstance(approval, dict) else None
    if isinstance(receipt, dict) and receipt:
        return validate_approval_receipt(case, project=project, manifest=manifest)
    package_path = project / "approval-package.json"
    if not package_path.is_file():
        return ["approval-package.json is missing"]
    package = load_json(package_path)
    expected = build_package(project, case, manifest)
    return [] if package == expected else ["approval package is stale or non-deterministic"]


def provider_timing_errors(project: Path, manifest: dict[str, Any]) -> list[str]:
    del manifest  # The frozen build report names every current provider artifact.
    build = load_json(project / "build_report.json")
    report, failures = provider_timing_report(project, build)
    if report.get("ok") is not True and not failures:
        return ["independent provider timing verification did not pass"]
    return failures


def editor_plan_errors(project: Path) -> list[str]:
    plan_path = project / "editor-plan.json"
    if not plan_path.is_file():
        return ["editor-plan.json is missing"]
    current = load_json(plan_path)
    expected = build_editor_plan(project)
    return [] if current == expected else ["editor-plan.json is stale or non-deterministic"]


def rendered_artifact_errors(project: Path) -> list[str]:
    build_path = project / "build_report.json"
    build = load_json(build_path)
    paths = {
        "videoSha256": project / str(build.get("video") or "renders/video.mp4"),
        "caseSha256": project / "case.json",
        "renderManifestSha256": project / "render-manifest.json",
        "alignmentReportSha256": project / str(
            build.get("alignmentReport") or "timing/alignment-report.json"
        ),
        "captionTimelineSha256": project / str(
            build.get("captionTimeline") or "timing/caption-timeline.json"
        ),
        "sceneTimelineSha256": project / str(
            build.get("sceneTimeline") or "timing/scene-timeline.json"
        ),
        "subtitleSha256": project / str(
            build.get("subtitleFile") or "timing/subtitles.ass"
        ),
        "narrationAudioSha256": project / str(
            build.get("narrationAudio") or "timing/narration.timestamped.final.wav"
        ),
        "rawNarrationAudioSha256": project / str(
            build.get("rawNarrationAudio") or "audio/narration.raw.wav"
        ),
        "ttsReportSha256": project / str(
            build.get("ttsReport") or "audio/narration.raw.wav.json"
        ),
        "wordTimelineSha256": project / str(
            build.get("wordTimeline") or "timing/word-timeline.json"
        ),
    }
    errors: list[str] = []
    for hash_field, path in paths.items():
        if not path.is_file():
            errors.append(f"render artifact is missing: {path}")
        elif str(build.get(hash_field) or "") != file_sha256(path):
            errors.append(f"build_report {hash_field} is missing or stale")
    audio_mix = project / str(build.get("audioMix") or "renders/audio_mix.m4a")
    if not audio_mix.is_file():
        errors.append(f"render artifact is missing: {audio_mix}")
    elif str(build.get("audioMixSha256") or "") != file_sha256(audio_mix):
        errors.append("build_report audioMixSha256 is missing or stale")
    return errors


def final_media_qa_errors(project: Path) -> list[str]:
    report = load_json(project / "renders/qa/qa-report.json")
    errors: list[str] = []
    if report.get("ok") is not True or report.get("structuralOk") is not True:
        errors.append("final QA report is not successful")
    if report.get("decodePassed") is not True:
        errors.append("final QA report does not record a complete decode")
    if report.get("failures"):
        errors.append("final QA report still contains failures")
    editable = report.get("editableDelivery")
    if not isinstance(editable, dict) or editable.get("ok") is not True:
        errors.append("final QA report editable delivery did not pass")
    visual_review = report.get("visualReview")
    if not isinstance(visual_review, dict) or visual_review.get("passed") is not True:
        errors.append("final QA report human visual review did not pass")
    provider_timing = report.get("providerTiming")
    if not isinstance(provider_timing, dict) or provider_timing.get("ok") is not True:
        errors.append("final QA report provider timing did not pass")
    elif provider_timing.get("failures") not in (None, []):
        errors.append("final QA report provider timing still contains failures")
    video_proof = report.get("video")
    if not isinstance(video_proof, dict):
        errors.append("final QA report video proof is missing")
        video_proof = {}
    video = project / "renders/video.mp4"
    if not video.is_file():
        errors.append("final QA video is missing")
    elif str(video_proof.get("sha256") or "") != file_sha256(video):
        errors.append("final QA report video hash is stale")
    audio = report.get("audio")
    if not isinstance(audio, dict):
        errors.append("final QA report audio proof is missing")
        audio = {}
    if audio.get("packetHashMatches") is not True:
        errors.append("final QA report packetHashMatches must be true")
    mix_relative = str(audio.get("mix") or "").strip()
    if not mix_relative:
        errors.append("final QA report audio mix path is missing")
    else:
        audio_mix = (project / mix_relative).resolve()
        try:
            audio_mix.relative_to(project.resolve())
        except ValueError:
            errors.append("final QA audio mix path escapes the project")
        else:
            if not audio_mix.is_file():
                errors.append(f"final QA audio mix is missing: {mix_relative}")
            elif str(audio.get("mixSha256") or "") != file_sha256(audio_mix):
                errors.append("final QA report audio mix hash is stale")
    return errors


def declared_assertions_for_stage(
    suite: dict[str, Any], stage: str
) -> dict[str, dict[str, Any]]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"unknown execution stage: {stage}")
    assertions = suite.get("executionAssertions")
    if not isinstance(assertions, list):
        raise ValueError("executionAssertions must be an array")
    seen: set[str] = set()
    active: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(assertions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"execution assertion {index} must be an object")
        assertion_id = str(item.get("id") or "").strip()
        if not assertion_id:
            raise ValueError(f"execution assertion {index} has no id")
        if assertion_id in seen:
            raise ValueError(f"duplicate execution assertion id: {assertion_id}")
        seen.add(assertion_id)
        assertion_stage = str(item.get("stage") or "").strip()
        if assertion_stage not in STAGE_ORDER:
            raise ValueError(
                f"execution assertion {assertion_id} has invalid stage: "
                f"{assertion_stage!r}"
            )
        for field in ("validator", "assertion"):
            if not str(item.get(field) or "").strip():
                raise ValueError(
                    f"execution assertion {assertion_id} has no {field}"
                )
        if STAGE_ORDER[assertion_stage] <= STAGE_ORDER[stage]:
            active[assertion_id] = item
    return active


def bind_declared_assertions(
    gates: list[dict[str, Any]], suite: dict[str, Any], stage: str
) -> list[str]:
    declared = declared_assertions_for_stage(suite, stage)
    scored_ids = [str(item.get("id") or "") for item in gates]
    if len(scored_ids) != len(set(scored_ids)):
        raise ValueError("execution scorer produced duplicate gate ids")
    scored = set(scored_ids)
    if set(declared) != scored:
        missing = sorted(set(declared) - scored)
        undeclared = sorted(scored - set(declared))
        raise ValueError(
            f"{stage} execution gates differ from eval declarations; "
            f"missing={missing}, undeclared={undeclared}"
        )
    for item in gates:
        declaration = declared[str(item["id"])]
        item["stage"] = declaration["stage"]
        item["validator"] = declaration["validator"]
        item["assertion"] = declaration["assertion"]
    return scored_ids


def score_project(project: Path, stage: str, suite: dict[str, Any]) -> dict[str, Any]:
    declared_assertions_for_stage(suite, stage)
    project = project.resolve()
    case = load_json(project / "case.json")
    manifest = load_json(project / "render-manifest.json")
    rank = STAGE_ORDER[stage]
    gates = [
        gate(
            "startup-policy",
            lambda: validate_visual_source_policy(case)
            + validate_visual_source_contract(case, manifest),
        ),
        gate(
            "draft-contract",
            lambda: validate_case(case, require_approved=False)
            + validate_caption_contract(case, manifest)
            + validate_visual_source_contract(case, manifest),
        ),
        gate(
            "approval-output",
            lambda: approval_output_errors(project, case, manifest),
        ),
    ]
    if rank >= STAGE_ORDER["synthesis"]:
        gates.append(
            gate(
                "approval-receipt",
                lambda: validate_case(
                    case,
                    require_approved=True,
                    project=project,
                    manifest=manifest,
                ),
            )
        )
    if rank >= STAGE_ORDER["render"]:
        gates.extend(
            [
                gate(
                    "render-assets",
                    lambda: validate_manifest(
                        project, case, manifest, check_assets=True
                    ),
                ),
                gate(
                    "provider-timestamps",
                    lambda: provider_timing_errors(project, manifest),
                ),
                gate("rendered-artifacts", lambda: rendered_artifact_errors(project)),
            ]
        )
    if rank >= STAGE_ORDER["delivery"]:
        editable_path = project / "editable-delivery.json"
        gates.extend(
            [
                gate("editor-plan", lambda: editor_plan_errors(project)),
                gate(
                    "editable-delivery",
                    lambda: (
                        validate_editable_delivery(
                            project, load_json(editable_path), strict=True
                        ).get("errors")
                        or []
                    ),
                ),
                gate("final-media-qa", lambda: final_media_qa_errors(project)),
                gate(
                    "delivery-freshness",
                    lambda: validate_delivery(project).get("errors") or [],
                ),
            ]
        )
    declared_ids = bind_declared_assertions(gates, suite, stage)
    passed = sum(1 for item in gates if item["passed"])
    pass_rate = passed / len(gates) if gates else 0.0
    threshold_document = suite.get("executionThresholds")
    if not isinstance(threshold_document, dict):
        raise ValueError("executionThresholds must be an object")
    try:
        threshold = float(threshold_document.get("minimumGatePassRate"))
        if not 0 <= threshold <= 1:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(
            "executionThresholds.minimumGatePassRate must be between 0 and 1"
        ) from None
    return {
        "ok": pass_rate >= threshold,
        "stage": stage,
        "project": str(project),
        "passedGates": passed,
        "totalGates": len(gates),
        "gatePassRate": pass_rate,
        "minimumGatePassRate": threshold,
        "declaredAssertionIds": declared_ids,
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--stage", choices=tuple(STAGE_ORDER), required=True)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()
    try:
        suite = load_json(args.suite.resolve())
        report = score_project(args.project, args.stage, suite)
    except (SystemExit, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        report = {"ok": False, "stage": args.stage, "errors": [str(exc)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
