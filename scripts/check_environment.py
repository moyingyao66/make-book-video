#!/usr/bin/env python3
"""Run a staged, read-only, secret-safe preflight for make-book-video."""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse


DOUBAO_KEYCHAIN_SERVICE = "codex.ai-self-media-video.DOUBAO_API_KEY"
WEREAD_KEYCHAIN_SERVICES = (
    "book-sales-video.WEREAD_API_KEY",
    "codex.book-sales-video.WEREAD_API_KEY",
)
PEXELS_KEYCHAIN_SERVICES = (
    "book-sales-video.PEXELS_API_KEY",
    "codex.book-sales-video.PEXELS_API_KEY",
    "codex.ai-self-media-video.PEXELS_API_KEY",
    "make-book-video.PEXELS_API_KEY",
)
STAGES = ("research", "visuals", "production", "editor", "all")


def secret_available(env_name: str, keychain_services: tuple[str, ...]) -> bool:
    """Return only availability; never expose a credential value."""
    if os.environ.get(env_name, "").strip():
        return True
    if platform.system() != "Darwin" or not shutil.which("security"):
        return False
    for keychain_service in keychain_services:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                getpass.getuser(),
                "-s",
                keychain_service,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
        if result.returncode == 0 and bool(result.stdout.strip()):
            return True
    return False


def skill_available(name: str) -> bool:
    """Search the supported user/workspace Skill roots, including system Skills."""
    roots = (
        Path.home() / ".codex/skills",
        Path.home() / ".codex/skills/.system",
        Path.home() / ".agents/skills",
        Path.cwd() / ".agents/skills",
    )
    return any((root / name / "SKILL.md").is_file() for root in roots)


def openchatcut_installations() -> list[str]:
    candidates = (
        Path("/Applications/OpenChatCut.app"),
        Path.home() / "Applications/OpenChatCut.app",
    )
    return [str(path) for path in candidates if path.exists()]


def ffmpeg_capabilities() -> dict[str, bool]:
    executable = shutil.which("ffmpeg")
    if not executable:
        return {"assFilter": False, "libx264Encoder": False, "aacEncoder": False}
    filters = subprocess.run(
        [executable, "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    encoders = subprocess.run(
        [executable, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    filter_text = filters.stdout + filters.stderr
    encoder_text = encoders.stdout + encoders.stderr
    return {
        "assFilter": " ass " in filter_text,
        "libx264Encoder": "libx264" in encoder_text,
        "aacEncoder": " aac " in encoder_text,
    }


def doubao_machine_status() -> dict[str, Any]:
    """Use the canonical machine preflight when installed; keep its raw output private."""
    executable = shutil.which("moying-doubao-config")
    if executable:
        result = subprocess.run(
            [executable, "status", "--require-ready"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        try:
            report = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            report = {}
        return {
            "commandAvailable": True,
            "ready": result.returncode == 0 and report.get("ready") is True,
            "browserLoginRequired": bool(report.get("browser_login_required")),
            "resourceIdConfigured": (report.get("resource_id") or {}).get("status")
            == "configured",
            "speakerConfigured": (report.get("speaker") or {}).get("status")
            == "configured",
            "valueExposed": False,
        }
    # Portable fallback for hosts that do not install the machine helper.
    return {
        "commandAvailable": False,
        "ready": secret_available("DOUBAO_API_KEY", (DOUBAO_KEYCHAIN_SERVICE,)),
        "browserLoginRequired": False,
        "resourceIdConfigured": bool(os.environ.get("DOUBAO_TTS_RESOURCE_ID", "").strip()),
        "speakerConfigured": bool(os.environ.get("DOUBAO_TTS_SPEAKER", "").strip()),
        "valueExposed": False,
    }


def chinese_font_available(font_name: str) -> bool:
    """Check common macOS fonts or fontconfig without trusting an ASS fallback."""
    normalized = font_name.strip().lower()
    mac_fonts = {
        "pingfang sc": Path("/System/Library/Fonts/PingFang.ttc"),
        "heiti sc": Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        "songti sc": Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    }
    if normalized in mac_fonts and mac_fonts[normalized].is_file():
        return True
    fc_match = shutil.which("fc-match")
    if not fc_match:
        return False
    result = subprocess.run(
        [fc_match, "-f", "%{family}", font_name],
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def load_project(project: Optional[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    if project is None:
        return {}, {}
    case_path = project / "case.json"
    manifest_path = project / "render-manifest.json"
    if not case_path.is_file():
        raise SystemExit(f"Missing case file: {case_path}")
    case = json.loads(case_path.read_text(encoding="utf-8"))
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    return case, manifest


def attributable_fallbacks_recorded(research_route: dict[str, Any]) -> bool:
    """Accept only a non-empty list of attributable HTTP(S) sources and reasons."""
    fallbacks = research_route.get("fallbacks")
    if not isinstance(fallbacks, list) or not fallbacks:
        return False
    for item in fallbacks:
        if not isinstance(item, dict):
            return False
        source_url = item.get("sourceUrl")
        reason = item.get("reason")
        if not isinstance(source_url, str) or not source_url.strip():
            return False
        parsed = urlparse(source_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        if not isinstance(reason, str) or not reason.strip():
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--stage", choices=STAGES, default="production")
    args = parser.parse_args()
    project = args.project.resolve() if args.project else None
    project_case, manifest = load_project(project)
    project_voice = project_case.get("voice") or {}
    visual_policy = project_case.get("visualSourcePolicy") or {}
    research_route = project_case.get("researchRoute") or {}

    requests_ready = importlib.util.find_spec("requests") is not None
    media_capabilities = ffmpeg_capabilities()
    doubao_status = doubao_machine_status()
    resource_id_ready = bool(str(project_voice.get("resourceId") or "").strip()) or bool(
        doubao_status["resourceIdConfigured"]
    )
    speaker_ready = bool(str(project_voice.get("speaker") or "").strip()) or bool(
        doubao_status["speakerConfigured"]
    )
    pexels_required = any(
        str(visual_policy.get(field) or "") == "pexels-video"
        for field in ("openingSource", "bodySource")
    )
    gpt_image_required = any(
        str(visual_policy.get(field) or "") == "gpt-image"
        for field in ("openingSource", "bodySource")
    )
    pexels_configured = secret_available("PEXELS_API_KEY", PEXELS_KEYCHAIN_SERVICES)
    weread_configured = secret_available("WEREAD_API_KEY", WEREAD_KEYCHAIN_SERVICES)
    input_mode = str(project_case.get("inputMode") or "")
    title_first_research = input_mode in {"book-title", "book-page"}
    research_status = str(research_route.get("status") or "")
    fallback_recorded = (
        research_status == "unavailable-with-fallback"
        and attributable_fallbacks_recorded(research_route)
    )
    font_name = str((manifest.get("captions") or {}).get("font") or "PingFang SC")
    font_ready = chinese_font_available(font_name)
    openchatcut = openchatcut_installations()
    chatcut_skill = skill_available("book-sales-video-chatcut")
    weread_skill_present = skill_available("weread-skills")
    weread_live_ready = weread_skill_present and weread_configured
    captured_weread = research_status == "captured"
    if not title_first_research:
        research_route_state = "not-required"
        research_degraded = False
        research_next_action = "continue-with-supplied-or-approved-source-material"
    elif research_status == "unavailable-with-fallback":
        if fallback_recorded:
            research_route_state = "fallback-recorded"
            research_degraded = True
            research_next_action = "continue-with-recorded-attributable-fallbacks"
        else:
            research_route_state = "fallback-required"
            research_degraded = True
            research_next_action = (
                "record-at-least-one-authoritative-fallback-sourceUrl-and-reason"
            )
    elif captured_weread or weread_live_ready:
        research_route_state = "weread-ready"
        research_degraded = False
        research_next_action = (
            "continue-with-recorded-weread-evidence"
            if captured_weread
            else "use-weread-first"
        )
    else:
        research_route_state = "fallback-required"
        research_degraded = True
        research_next_action = (
            "attempt-weread-first-then-record-authoritative-fallback-sources"
        )
    weread_primary_route_required = (
        title_first_research
        and not captured_weread
        and not fallback_recorded
    )
    imagegen_local_present = skill_available("imagegen")
    editor_local_present = bool(openchatcut) or chatcut_skill

    checks = {
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "supported": sys.version_info >= (3, 8),
        },
        "pythonRequests": requests_ready,
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "ffmpegCapabilities": media_capabilities,
        "captionFont": {"name": font_name, "available": font_ready},
        "doubaoMachineConfig": doubao_status,
        "doubaoResourceId": resource_id_ready,
        "doubaoSpeaker": speaker_ready,
        "wereadSkill": weread_skill_present,
        "wereadApiKey": {
            "configured": weread_configured,
            "required": weread_primary_route_required,
            "blocking": False,
            "valueExposed": False,
        },
        "researchRoute": {
            "primary": "weread-skills" if title_first_research else None,
            "routeState": research_route_state,
            "degraded": research_degraded,
            "nextAction": research_next_action,
            "fallbackDeclared": research_status == "unavailable-with-fallback",
            "fallbackRecorded": fallback_recorded,
        },
        "imagegenSkill": {
            "available": imagegen_local_present,
            "required": gpt_image_required,
            "liveToolCheckRequired": gpt_image_required,
            "liveVerified": False,
            "availabilityState": (
                "local-present-live-unverified"
                if imagegen_local_present
                else "local-missing"
            ),
        },
        "pexelsApiKey": {
            "configured": pexels_configured,
            "required": pexels_required,
            "valueExposed": False,
        },
        "visualSourcePolicy": {
            "confirmed": visual_policy.get("selectionStatus") == "confirmed",
            "openingSource": visual_policy.get("openingSource"),
            "bodySource": visual_policy.get("bodySource"),
        },
        "editableDelivery": {
            "openchatcutLocalInstallations": openchatcut,
            "lsof": shutil.which("lsof"),
            "chatcutBookVideoSkill": chatcut_skill,
            "routeAvailable": editor_local_present,
            "routeAvailabilityScope": "local-only",
            "liveVerified": False,
            "availabilityState": (
                "local-present-live-unverified"
                if editor_local_present
                else "local-missing"
            ),
            "liveAuthenticationCheckRequired": True,
        },
    }

    python_ready = bool(checks["python"]["supported"])
    # A missing WeRead route is degraded but actionable: research can continue by
    # finding and recording attributable authoritative fallback sources.
    research_ready = python_ready
    visuals_local_ready = (
        project is not None
        and bool(checks["visualSourcePolicy"]["confirmed"])
        and (pexels_configured if pexels_required else True)
        and (imagegen_local_present if gpt_image_required else True)
    )
    # A local Skill proves discoverability only. The host must still perform a
    # live image generation check before the visual stage can be called ready.
    visuals_ready = visuals_local_ready and not gpt_image_required
    production_ready = all(
        [
            python_ready,
            requests_ready,
            bool(checks["ffmpeg"]),
            bool(checks["ffprobe"]),
            all(media_capabilities.values()),
            font_ready,
            bool(doubao_status["ready"]),
            resource_id_ready,
            speaker_ready,
        ]
    )
    # A local app/Skill installation does not prove authentication, mutation, or
    # project readback. Keep production independent from this live editor gate.
    editor_ready = False
    ready_by_stage = {
        "research": research_ready,
        "visuals": visuals_ready,
        "production": production_ready,
        "editor": editor_ready,
    }
    if not python_ready:
        research_stage_state = "blocked-local-prerequisite-missing"
    elif research_degraded:
        research_stage_state = "degraded"
    else:
        research_stage_state = "ready"
    if not visuals_local_ready:
        visuals_stage_state = "blocked-local-prerequisite-missing"
    elif gpt_image_required:
        visuals_stage_state = "local-present-live-unverified"
    else:
        visuals_stage_state = "ready"
    production_stage_state = (
        "ready" if production_ready else "blocked-local-prerequisite-missing"
    )
    editor_stage_state = (
        "local-present-live-unverified"
        if editor_local_present
        else "blocked-local-prerequisite-missing"
    )
    required_live_checks: list[dict[str, Any]] = []
    if gpt_image_required:
        required_live_checks.append(
            {
                "stage": "visuals",
                "capability": "imagegen",
                "state": "required",
                "reason": "local Skill discovery does not prove a live generation call",
            }
        )
    required_live_checks.append(
        {
            "stage": "editor",
            "capability": "editable-project-write-and-readback",
            "state": "required",
            "reason": "local editor discovery does not prove authentication or editable project readback",
        }
    )
    stage_states = {
        "research": {
            "state": research_stage_state,
            "ready": research_ready,
            "routeState": research_route_state,
            "degraded": research_degraded,
            "nextAction": research_next_action,
        },
        "visuals": {
            "state": visuals_stage_state,
            "ready": visuals_ready,
            "degraded": False,
            "nextAction": (
                "perform-live-imagegen-check"
                if visuals_stage_state == "local-present-live-unverified"
                else (
                    "resolve-local-or-configured-visual-dependencies"
                    if not visuals_ready
                    else "continue"
                )
            ),
        },
        "production": {
            "state": production_stage_state,
            "ready": production_ready,
            "degraded": False,
            "nextAction": (
                "continue" if production_ready else "resolve-production-dependencies"
            ),
        },
        "editor": {
            "state": editor_stage_state,
            "ready": editor_ready,
            "degraded": False,
            "nextAction": (
                "perform-live-editor-auth-write-and-readback-check"
                if editor_local_present
                else "install-an-editable-delivery-route"
            ),
        },
    }
    requested_ready = (
        all(ready_by_stage.values()) if args.stage == "all" else ready_by_stage[args.stage]
    )
    result = {
        "version": 3,
        "skill": "make-book-video",
        "project": str(project) if project else None,
        "requestedStage": args.stage,
        "ready": requested_ready,
        "readyByStage": ready_by_stage,
        "stageStates": stage_states,
        "requiredLiveChecks": required_live_checks,
        # Compatibility fields retained for existing callers.
        "readyForTimestampedNarration": production_ready,
        "readyForSelectedVisualSources": visuals_ready,
        "readyForBuild": production_ready,
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if requested_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
