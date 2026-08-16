#!/usr/bin/env python3
"""Run a read-only, secret-safe preflight for make-book-video."""

from __future__ import annotations

import argparse
import importlib.util
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


DOUBAO_KEYCHAIN_SERVICE = "codex.ai-self-media-video.DOUBAO_API_KEY"
WEREAD_KEYCHAIN_SERVICES = (
    "book-sales-video.WEREAD_API_KEY",
    "codex.book-sales-video.WEREAD_API_KEY",
)


def secret_available(env_name: str, keychain_services: tuple[str, ...]) -> bool:
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
    roots = [Path.home() / ".codex/skills", Path.home() / ".agents/skills"]
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    args = parser.parse_args()
    project_voice: dict = {}
    if args.project:
        case_path = args.project.resolve() / "case.json"
        if not case_path.is_file():
            raise SystemExit(f"Missing case file: {case_path}")
        project_voice = (
            json.loads(case_path.read_text(encoding="utf-8")).get("voice") or {}
        )
    requests_ready = importlib.util.find_spec("requests") is not None
    resource_id_ready = bool(
        str(project_voice.get("resourceId") or os.environ.get("DOUBAO_TTS_RESOURCE_ID", "")).strip()
    )
    speaker_ready = bool(
        str(project_voice.get("speaker") or os.environ.get("DOUBAO_TTS_SPEAKER", "")).strip()
    )
    media_capabilities = ffmpeg_capabilities()
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
        "doubaoApiKey": {
            "configured": secret_available("DOUBAO_API_KEY", (DOUBAO_KEYCHAIN_SERVICE,)),
            "valueExposed": False,
        },
        "doubaoResourceId": resource_id_ready,
        "doubaoSpeaker": speaker_ready,
        "wereadSkill": skill_available("weread-skills"),
        "wereadApiKey": {
            "configured": secret_available("WEREAD_API_KEY", WEREAD_KEYCHAIN_SERVICES),
            "valueExposed": False,
        },
        "pexelsApiKey": {
            "configured": bool(os.environ.get("PEXELS_API_KEY", "").strip()),
            "required": False,
            "valueExposed": False,
        },
        "editableDelivery": {
            "openchatcutLocalInstallations": openchatcut_installations(),
            "chatcutBookVideoSkill": skill_available("book-sales-video-chatcut"),
            "runtimeSchemaCheckRequired": True,
        },
    }
    required = [
        checks["python"]["supported"],
        requests_ready,
        bool(checks["ffmpeg"]),
        bool(checks["ffprobe"]),
        all(media_capabilities.values()),
        checks["doubaoApiKey"]["configured"],
        resource_id_ready,
        speaker_ready,
    ]
    result = {
        "skill": "make-book-video",
        "project": str(args.project.resolve()) if args.project else None,
        "readyForTimestampedNarration": all(required),
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(required) else 2


if __name__ == "__main__":
    raise SystemExit(main())
