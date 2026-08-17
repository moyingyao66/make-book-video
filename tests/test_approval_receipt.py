#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

from validate_case import validate_case, validate_manifest  # noqa: E402
from test_copy_contract import version_three_visual_fixture  # noqa: E402


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_preview(path: Path, amplitude: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = int(amplitude).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        target.writeframes(sample * 2400)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_preview_report(project: Path, case: dict, **overrides: object) -> None:
    preview = project / "audio/voice-preview.wav"
    voice = case["voice"]
    report = {
        "audioSha256": sha256(preview),
        "resourceId": voice["resourceId"],
        "speaker": voice["speaker"],
        "speechRate": voice["speechRate"],
        "enableSubtitle": voice["enableSubtitle"],
    }
    report.update(overrides)
    write_json(project / "audio/voice-preview.wav.json", report)


def prepare_draft_project(project: Path) -> tuple[dict, dict]:
    case, visual_manifest = version_three_visual_fixture(
        opening_source="gpt-image", body_source="gpt-image"
    )
    case["status"] = "draft"
    case["approval"] = {
        "contentApprovedByUser": False,
        "storyboardApprovedByUser": False,
        "paidGenerationAuthorized": False,
        "receipt": {},
    }
    manifest = {
        "version": 3,
        "canvas": case["canvas"],
        "sceneAssets": visual_manifest["sceneAssets"],
        "captions": {
            "mode": "zh-only",
            "requireEnglish": False,
            "burnIn": True,
            "fontSize": 72,
            "englishFontSize": 40,
            "positionY": 1500,
            "safeBottomPx": 360,
        },
    }
    write_json(project / "case.json", case)
    write_json(project / "render-manifest.json", manifest)
    write_preview(project / "audio/voice-preview.wav")
    write_preview_report(project, case)
    package = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_approval_package.py"), str(project)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if package.returncode != 0:
        raise AssertionError(package.stdout + package.stderr)
    return case, manifest


def record_approval(project: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "record_approval.py"),
            str(project),
            "--approved-by",
            "test-user",
            "--approved-at",
            "2026-08-17T12:00:00+09:00",
            "--voice-preview",
            "audio/voice-preview.wav",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            **(extra_env or {}),
        },
    )


def load_approved(project: Path) -> tuple[dict, dict]:
    result = record_approval(project)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    case = json.loads((project / "case.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (project / "render-manifest.json").read_text(encoding="utf-8")
    )
    return case, manifest


class ApprovalReceiptTests(unittest.TestCase):
    def test_render_rejects_pending_asset_status_but_draft_remains_editable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            case, manifest = prepare_draft_project(project)
            manifest["sceneAssets"]["intro"][
                "assetStatus"
            ] = "pending-semantic-review"
            draft_errors = validate_case(case, require_approved=False)
            self.assertFalse(
                any("assetStatus must be reviewed" in error for error in draft_errors),
                draft_errors,
            )
            render_errors = validate_manifest(
                project, case, manifest, check_assets=True
            )
            self.assertTrue(
                any(
                    "scene intro assetStatus must be reviewed before render" in error
                    for error in render_errors
                ),
                render_errors,
            )

    def test_version_three_requires_narrative_profile_and_approved_receipt(self) -> None:
        case, _ = version_three_visual_fixture(
            opening_source="gpt-image", body_source="gpt-image"
        )
        case["status"] = "draft"
        case.pop("narrativeProfile")
        errors = validate_case(case, require_approved=False)
        self.assertIn("version 3 projects require narrativeProfile.id", errors)

        case, _ = version_three_visual_fixture(
            opening_source="gpt-image", body_source="gpt-image"
        )
        errors = validate_case(case, require_approved=True)
        self.assertIn(
            "approval.receipt is required for approved version 3 projects", errors
        )

    def test_record_approval_binds_current_sources_without_leaking_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            secret = "must-not-appear-in-approval-output"
            result = record_approval(project, {"DOUBAO_API_KEY": secret})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn(secret, result.stdout + result.stderr)
            case = json.loads((project / "case.json").read_text(encoding="utf-8"))
            manifest = json.loads(
                (project / "render-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(case["status"], "approved-for-generation")
            self.assertTrue(case["approval"]["paidGenerationAuthorized"])
            receipt = case["approval"]["receipt"]
            self.assertEqual(receipt["approvedBy"], "test-user")
            self.assertEqual(
                receipt["voicePreview"]["path"], "audio/voice-preview.wav"
            )
            self.assertEqual(
                receipt["voicePreview"]["report"]["path"],
                "audio/voice-preview.wav.json",
            )
            self.assertEqual(
                validate_case(
                    case,
                    require_approved=True,
                    project=project,
                    manifest=manifest,
                ),
                [],
            )
            synthesis = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_case.py"),
                    str(project),
                    "--stage",
                    "synthesis",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(
                synthesis.returncode, 0, synthesis.stdout + synthesis.stderr
            )

    def test_case_storyboard_and_voice_mutations_invalidate_receipt(self) -> None:
        mutations: list[tuple[str, Callable[[dict], None], str]] = [
            (
                "narration",
                lambda case: case["segments"][2].update(
                    {"narration": case["segments"][2]["narration"] + "变化"}
                ),
                "case content projection is stale",
            ),
            (
                "storyboard",
                lambda case: case["segments"][2].update(
                    {"visualIntent": "changed visual intent"}
                ),
                "case content projection is stale",
            ),
            (
                "voice",
                lambda case: case["voice"].update({"speaker": "changed-speaker"}),
                "voice configuration is stale",
            ),
        ]
        for label, mutate, expected in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepare_draft_project(project)
                case, manifest = load_approved(project)
                mutate(case)
                errors = validate_case(
                    case,
                    require_approved=True,
                    project=project,
                    manifest=manifest,
                )
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_manifest_preview_and_package_mutations_invalidate_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            case, manifest = load_approved(project)
            manifest["sceneAssets"]["intro"]["intent"] = "changed manifest intent"
            errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            self.assertTrue(
                any("manifest semantic projection is stale" in error for error in errors),
                errors,
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            _, manifest = prepare_draft_project(project)
            manifest["sceneAssets"]["intro"]["overlays"] = [
                {"path": "assets/covers/main.png", "x": 100, "y": 200}
            ]
            write_json(project / "render-manifest.json", manifest)
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_approval_package.py"), str(project)],
                check=True,
                capture_output=True,
                text=True,
            )
            case, manifest = load_approved(project)
            manifest["sceneAssets"]["intro"]["overlays"][0]["x"] = 600
            errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            self.assertTrue(
                any("manifest semantic projection is stale" in error for error in errors),
                errors,
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            case, manifest = load_approved(project)
            write_preview(project / "audio/voice-preview.wav", amplitude=100)
            errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            self.assertIn("approval voice preview hash is stale", errors)

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            case, manifest = load_approved(project)
            package_path = project / "approval-package.json"
            package_path.write_text(
                package_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
            )
            errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            self.assertIn("approval package hash is stale", errors)

    def test_replaced_or_voice_mismatched_preview_report_invalidates_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            case, manifest = load_approved(project)
            write_preview_report(project, case, requestId="replacement-report")
            errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            self.assertIn("approval voice preview report hash is stale", errors)

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            case, manifest = load_approved(project)
            write_preview_report(project, case, speaker="forged-speaker")
            report_path = project / "audio/voice-preview.wav.json"
            case["approval"]["receipt"]["voicePreview"]["report"][
                "sha256"
            ] = sha256(report_path)
            errors = validate_case(
                case,
                require_approved=True,
                project=project,
                manifest=manifest,
            )
            self.assertIn(
                "approval voice preview report speaker differs from case.voice", errors
            )

    def test_record_approval_rejects_preview_report_for_another_voice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            case, _ = prepare_draft_project(project)
            write_preview_report(project, case, speechRate=99)
            result = record_approval(project)
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("speechRate differs" in error for error in report["errors"]),
                report,
            )
            current = json.loads((project / "case.json").read_text(encoding="utf-8"))
            self.assertEqual(current["status"], "draft")

    def test_record_approval_rejects_a_stale_approval_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            case = json.loads((project / "case.json").read_text(encoding="utf-8"))
            case["angle"] = "changed after package generation"
            write_json(project / "case.json", case)
            result = record_approval(project)
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("case source hash is stale" in error for error in report["errors"]),
                report,
            )
            current = json.loads((project / "case.json").read_text(encoding="utf-8"))
            self.assertEqual(current["status"], "draft")

    def test_build_video_rechecks_preview_before_any_paid_tts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_draft_project(project)
            load_approved(project)
            write_preview(project / "audio/voice-preview.wav", amplitude=200)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "build_video.py"), str(project)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("approval voice preview hash is stale", result.stderr)
            self.assertFalse((project / "narration.txt").exists())
            self.assertFalse((project / "audio/narration.raw.wav").exists())


if __name__ == "__main__":
    unittest.main()
