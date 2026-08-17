#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
VERIFIER = SCRIPTS / "verify_release.py"
sys.path.insert(0, str(ROOT / "tests"))

from test_generic_pipeline import (  # noqa: E402
    prepare_project,
    sha256,
    write_json,
    write_verified_editable_delivery,
)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class ReleaseVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._base_temp = tempfile.TemporaryDirectory()
        cls.base_project = Path(cls._base_temp.name) / "verified-project"
        prepare_project(cls.base_project, release_ready=True)
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "build_video.py"),
                str(cls.base_project),
                "--render-only",
            ],
            check=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
        )
        write_verified_editable_delivery(cls.base_project)
        review_path = cls.base_project / "renders/qa/human-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["passed"] = True
        review["reviewedAt"] = "2026-01-01T00:00:00Z"
        review["reviewer"] = "release-verifier-test"
        review["editableDeliverySha256"] = sha256(
            cls.base_project / "editable-delivery.json"
        )
        review["checks"] = {key: True for key in review["checks"]}
        write_json(review_path, review)
        subprocess.run(
            [sys.executable, str(SCRIPTS / "qa_video.py"), str(cls.base_project)],
            check=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._base_temp.cleanup()

    def copy_project(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        project = Path(temporary.name) / "project"
        shutil.copytree(self.base_project, project)
        return project

    def run_verifier(self, project: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
        result = subprocess.run(
            [sys.executable, str(VERIFIER), str(project)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic guard
            self.fail(f"verifier returned non-JSON output: {exc}\n{result.stdout}\n{result.stderr}")
        return result, report

    def rewrite_release_hash(self, project: Path, field: str, path: Path) -> dict:
        marker_path = project / "renders/qa/release-ready.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker[field] = sha256(path)
        write_json(marker_path, marker)
        return marker

    def test_current_real_release_passes_independent_verification(self) -> None:
        project = self.copy_project()
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["independentMedia"]["ffprobePassed"])
        self.assertTrue(report["independentMedia"]["decodePassed"])
        self.assertTrue(report["independentMedia"]["packetHashMatches"])
        self.assertTrue(report["independentProviderTiming"]["ok"])
        self.assertTrue(report["independentEditableDelivery"]["ok"])
        self.assertTrue(report["independentContactSheets"]["ok"])
        self.assertTrue(report["independentEditorPlan"]["ok"])
        inventory_roles = {
            item["role"]
            for item in report["independentRenderInputInventory"]["entries"]
        }
        self.assertTrue(
            {
                "scene.scene-1.primary",
                "scene.scene-1.overlay[0]",
                "scene.scene-2.carousel[0]",
                "audio.bgm",
                "audio.sfx[0]",
                "captions.ass",
                "timing.scene-timeline",
                "approval.voice-preview",
                "approval.voice-preview-report",
                "approval.package",
            }.issubset(inventory_roles)
        )

    def test_asset_replacement_requires_rerender_even_without_editable_ledger_trust(self) -> None:
        project = self.copy_project()
        visual = project / "assets/covers/one.ppm"
        visual.write_bytes(visual.read_bytes() + b"replaced-after-render")
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("render input inventory source hash changed" in error for error in report["errors"]),
            report,
        )

    def test_case_symlink_outside_project_is_rejected(self) -> None:
        project = self.copy_project()
        case_path = project / "case.json"
        outside = project.parent / "outside-case.json"
        outside.write_bytes(case_path.read_bytes())
        case_path.unlink()
        case_path.symlink_to(outside)
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("case.json must not be a symlink" in error for error in report["errors"]),
            report,
        )

    def test_deleted_voice_preview_invalidates_release_receipt_and_inventory(self) -> None:
        project = self.copy_project()
        case = json.loads((project / "case.json").read_text(encoding="utf-8"))
        preview = project / case["approval"]["receipt"]["voicePreview"]["path"]
        preview.unlink()
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any(
                "voice preview" in error or "approval.voice-preview" in error
                for error in report["errors"]
            ),
            report,
        )

    def test_deleted_approval_package_invalidates_release_receipt_and_inventory(self) -> None:
        project = self.copy_project()
        case = json.loads((project / "case.json").read_text(encoding="utf-8"))
        package = project / case["approval"]["receipt"]["approvalPackage"]["path"]
        package.unlink()
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any(
                "approval package" in error or "approval.package" in error
                for error in report["errors"]
            ),
            report,
        )

    def test_forged_contact_sheet_ledgers_cannot_replace_video_derived_evidence(self) -> None:
        project = self.copy_project()
        contact = project / "renders/qa/final-contact-sheet.png"
        replacement = project / "renders/qa/editor-opening.png"
        shutil.copyfile(replacement, contact)
        replacement_hash = sha256(contact)

        marker_path = project / "renders/qa/release-ready.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        for item in marker["humanEvidence"]:
            if item["path"] == "renders/qa/final-contact-sheet.png":
                item["sha256"] = replacement_hash

        qa_path = project / "renders/qa/qa-report.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        qa["humanEvidence"] = marker["humanEvidence"]
        write_json(qa_path, qa)
        marker["qaReportSha256"] = sha256(qa_path)
        write_json(marker_path, marker)

        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("does not match the current video" in error for error in report["errors"]),
            report,
        )

    def test_stale_editor_plan_is_rejected_without_treating_plan_as_execution(self) -> None:
        project = self.copy_project()
        plan_path = project / "editor-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["status"] = "verified"
        plan["editorExecutionClaimed"] = True
        write_json(plan_path, plan)

        qa_path = project / "renders/qa/qa-report.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        qa["editorPlan"].update(
            {
                "sha256": sha256(plan_path),
                "status": "verified",
                "editorExecutionClaimed": True,
            }
        )
        write_json(qa_path, qa)

        marker_path = project / "renders/qa/release-ready.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["editorPlanSha256"] = sha256(plan_path)
        marker["qaReportSha256"] = sha256(qa_path)
        write_json(marker_path, marker)

        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("editor plan differs" in error or "must not claim" in error for error in report["errors"]),
            report,
        )

    def test_malformed_nested_shapes_return_json_failure_without_traceback(self) -> None:
        mutations = ("qa-video", "build-scenes", "human-checks")
        for label in mutations:
            with self.subTest(label=label):
                project = self.copy_project()
                marker_path = project / "renders/qa/release-ready.json"
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if label == "qa-video":
                    qa_path = project / "renders/qa/qa-report.json"
                    qa = json.loads(qa_path.read_text(encoding="utf-8"))
                    qa["video"] = ["malformed"]
                    write_json(qa_path, qa)
                    marker["qaReportSha256"] = sha256(qa_path)
                elif label == "build-scenes":
                    build_path = project / "build_report.json"
                    build = json.loads(build_path.read_text(encoding="utf-8"))
                    build["scenes"] = ["malformed"]
                    write_json(build_path, build)
                    marker["buildReportSha256"] = sha256(build_path)
                else:
                    human_path = project / "renders/qa/human-review.json"
                    human = json.loads(human_path.read_text(encoding="utf-8"))
                    human["checks"] = ["malformed"]
                    write_json(human_path, human)
                    qa_path = project / "renders/qa/qa-report.json"
                    qa = json.loads(qa_path.read_text(encoding="utf-8"))
                    qa["visualReview"] = human
                    write_json(qa_path, qa)
                    marker["humanReviewSha256"] = sha256(human_path)
                    marker["qaReportSha256"] = sha256(qa_path)
                write_json(marker_path, marker)
                result, report = self.run_verifier(project)
                self.assertEqual(result.returncode, 2, report)
                self.assertFalse(report["ok"], report)
                self.assertNotIn("Traceback", result.stderr)

    def test_top_level_artifact_change_invalidates_release(self) -> None:
        project = self.copy_project()
        editable = project / "editable-delivery.json"
        editable.write_bytes(editable.read_bytes() + b" ")
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("editableDeliverySha256" in error for error in report["errors"]),
            report,
        )

    def test_nested_editor_evidence_change_invalidates_release(self) -> None:
        project = self.copy_project()
        editable = json.loads((project / "editable-delivery.json").read_text(encoding="utf-8"))
        evidence = project / editable["verificationFrames"][0]["evidencePath"]
        evidence.write_bytes(evidence.read_bytes() + b"stale")
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("evidence SHA256" in error for error in report["errors"]), report
        )

    def test_visual_source_change_invalidates_release(self) -> None:
        project = self.copy_project()
        visual = project / "visuals/intro.ppm"
        visual.write_bytes(visual.read_bytes() + b"stale")
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("sourceSha256" in error for error in report["errors"]), report
        )

    def test_human_evidence_change_invalidates_release(self) -> None:
        project = self.copy_project()
        contact_sheet = project / "renders/qa/final-contact-sheet.png"
        contact_sheet.write_bytes(contact_sheet.read_bytes() + b"stale")
        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("human evidence hash is stale" in error for error in report["errors"]),
            report,
        )

    def test_forged_json_cannot_make_a_non_media_file_release_ready(self) -> None:
        project = self.copy_project()
        video = project / "renders/video.mp4"
        video.write_bytes(b"not-a-playable-mp4")
        video_hash = sha256(video)

        build_path = project / "build_report.json"
        build = json.loads(build_path.read_text(encoding="utf-8"))
        build["videoSha256"] = video_hash
        write_json(build_path, build)

        human_path = project / "renders/qa/human-review.json"
        human = json.loads(human_path.read_text(encoding="utf-8"))
        human["videoSha256"] = video_hash
        write_json(human_path, human)

        qa_path = project / "renders/qa/qa-report.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        qa["video"]["sha256"] = video_hash
        qa["visualReview"] = human
        write_json(qa_path, qa)

        marker_path = project / "renders/qa/release-ready.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["videoSha256"] = video_hash
        marker["buildReportSha256"] = sha256(build_path)
        marker["humanReviewSha256"] = sha256(human_path)
        marker["qaReportSha256"] = sha256(qa_path)
        write_json(marker_path, marker)

        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("ffprobe failed" in error for error in report["errors"]), report
        )

    def test_forged_provider_pass_claim_is_rejected(self) -> None:
        project = self.copy_project()
        qa_path = project / "renders/qa/qa-report.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        qa["providerTiming"] = {**qa["providerTiming"], "ok": False}
        write_json(qa_path, qa)
        self.rewrite_release_hash(project, "qaReportSha256", qa_path)

        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("providerTiming differs" in error for error in report["errors"]), report
        )

    def test_missing_human_check_is_rejected_even_when_hashes_are_rewritten(self) -> None:
        project = self.copy_project()
        human_path = project / "renders/qa/human-review.json"
        human = json.loads(human_path.read_text(encoding="utf-8"))
        human["checks"]["captionSync"] = False
        write_json(human_path, human)

        qa_path = project / "renders/qa/qa-report.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        qa["visualReview"] = human
        write_json(qa_path, qa)

        marker_path = project / "renders/qa/release-ready.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["humanReviewSha256"] = sha256(human_path)
        marker["qaReportSha256"] = sha256(qa_path)
        write_json(marker_path, marker)

        result, report = self.run_verifier(project)
        self.assertEqual(result.returncode, 2, report)
        self.assertTrue(
            any("captionSync" in error for error in report["errors"]), report
        )


if __name__ == "__main__":
    unittest.main()
