#!/usr/bin/env python3
"""Run a read-only, secret-safe preflight for make-book-video."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


KEYCHAIN_SERVICE = "codex.ai-self-media-video.DOUBAO_API_KEY"


def key_available() -> bool:
    if os.environ.get("DOUBAO_API_KEY", "").strip():
        return True
    if platform.system() != "Darwin" or not shutil.which("security"):
        return False
    result = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def skill_available(name: str) -> bool:
    roots = [Path.home() / ".codex/skills", Path.home() / ".agents/skills"]
    return any((root / name / "SKILL.md").is_file() for root in roots)


def main() -> int:
    requests_ready = importlib.util.find_spec("requests") is not None
    checks = {
        "pythonRequests": requests_ready,
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "doubaoApiKey": {"configured": key_available(), "valueExposed": False},
        "doubaoResourceId": bool(os.environ.get("DOUBAO_TTS_RESOURCE_ID", "").strip()),
        "doubaoSpeaker": bool(os.environ.get("DOUBAO_TTS_SPEAKER", "").strip()),
        "wereadSkill": skill_available("weread-skills"),
        "wereadApiKey": {
            "configured": bool(os.environ.get("WEREAD_API_KEY", "").strip()),
            "valueExposed": False,
        },
        "pexelsApiKey": {
            "configured": bool(os.environ.get("PEXELS_API_KEY", "").strip()),
            "required": False,
            "valueExposed": False,
        },
    }
    required = [
        requests_ready,
        bool(checks["ffmpeg"]),
        bool(checks["ffprobe"]),
        checks["doubaoApiKey"]["configured"],
    ]
    result = {
        "skill": "make-book-video",
        "readyForTimestampedNarration": all(required),
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(required) else 2


if __name__ == "__main__":
    raise SystemExit(main())
