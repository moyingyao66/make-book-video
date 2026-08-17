#!/usr/bin/env python3
"""Run the generic approved-case pipeline through render, or finalize media QA."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from project_artifacts import ProjectArtifactError, secure_project_file
from validate_case import validate_caption_contract, validate_case


SCRIPT_DIR = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--render-only", action="store_true")
    mode.add_argument("--qa-only", action="store_true")
    parser.add_argument("--force-tts", action="store_true")
    args = parser.parse_args()
    project = args.project.resolve()

    if args.qa_only:
        run([sys.executable, str(SCRIPT_DIR / "qa_video.py"), str(project)])
        return 0

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
        manifest = {}
    else:
        manifest_error = ""
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_case(
        case,
        require_approved=True,
        project=project,
        manifest=manifest if not manifest_error else None,
    )
    if manifest_error:
        errors.append(manifest_error)
    else:
        errors.extend(validate_caption_contract(case, manifest))
    if errors:
        raise SystemExit("Approved-case validation failed: " + "; ".join(errors))

    if not args.render_only:
        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "check_environment.py"),
                "--project",
                str(project),
                "--stage",
                "production",
            ]
        )
        narration_text = "\n".join(
            str(segment.get("narration") or "").strip()
            for segment in case.get("segments") or []
        ).strip()
        narration_path = project / "narration.txt"
        narration_path.write_text(narration_text + "\n", encoding="utf-8")
        voice = case.get("voice") or {}
        canvas = case.get("canvas") or {}
        caption_style = manifest.get("captions") or {}
        raw_audio = project / "audio/narration.raw.wav"
        tts_command = [
            sys.executable,
            str(SCRIPT_DIR / "doubao_tts.py"),
            "--text-file",
            str(narration_path),
            "--output",
            str(raw_audio),
            "--resource-id",
            str(voice["resourceId"]),
            "--speaker",
            str(voice["speaker"]),
            "--speech-rate",
            str(int(voice["speechRate"])),
            "--sample-rate",
            str(int(voice.get("sampleRate") or 24000)),
            "--retries",
            "1",
        ]
        if args.force_tts:
            tts_command.append("--force")
        run(tts_command)
        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "build_timestamp_timeline.py"),
                "--audio",
                str(raw_audio),
                "--tts-report",
                str(raw_audio.with_suffix(raw_audio.suffix + ".json")),
                "--storyboard",
                str(case_path),
                "--case",
                str(case_path),
                "--output-dir",
                str(project / "timing"),
                "--fps",
                str(int(canvas["fps"])),
                "--caption-font",
                str(caption_style.get("font") or "PingFang SC"),
                "--caption-font-size",
                str(int(caption_style.get("fontSize") or 72)),
                "--english-font-size",
                str(int(caption_style.get("englishFontSize") or 40)),
                "--caption-position-y",
                str(int(caption_style.get("positionY") or round(int(canvas["height"]) * 0.78125))),
            ]
        )

    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "validate_case.py"),
            str(project),
            "--stage",
            "render",
        ]
    )
    run([sys.executable, str(SCRIPT_DIR / "render_video.py"), str(project)])
    run([sys.executable, str(SCRIPT_DIR / "build_editor_plan.py"), str(project)])
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "qa_video.py"),
            str(project),
            "--prepare-review",
        ]
    )
    print(
        "Render and structural QA complete. Build and read back the editable editor project, update "
        "editable-delivery.json, review renders/video.mp4 plus the editor composition, complete "
        "renders/qa/human-review.json, then run --qa-only."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
