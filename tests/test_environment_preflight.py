#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_environment.py"


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")


class EnvironmentPreflightTests(unittest.TestCase):
    def project(self, root: Path) -> Path:
        project = root / "project"
        write_json(
            project / "case.json",
            {
                "inputMode": "book-title",
                "researchRoute": {"status": "pending"},
                "visualSourcePolicy": {
                    "selectionStatus": "confirmed",
                    "openingSource": "pexels-video",
                    "bodySource": "gpt-image",
                },
                "voice": {"resourceId": "seed-tts-2.0", "speaker": "test"},
            },
        )
        write_json(
            project / "render-manifest.json",
            {"captions": {"font": "PingFang SC"}},
        )
        return project

    def run_stage(self, project: Path, stage: str, extra_env=None, *, full=True):
        environment = {
            **os.environ,
            # Keep the test independent from this machine's Keychain and media tools.
            "PATH": "/bin",
            "WEREAD_API_KEY": "",
            "PEXELS_API_KEY": "",
            "DOUBAO_API_KEY": "",
            "DOUBAO_TTS_RESOURCE_ID": "",
            "DOUBAO_TTS_SPEAKER": "",
            **(extra_env or {}),
        }
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--project",
                str(project),
                "--stage",
                stage,
                *(["--full"] if full else []),
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed, json.loads(completed.stdout)

    def test_research_gate_is_independent_from_later_media_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            completed, report = self.run_stage(
                project, "research", {"WEREAD_API_KEY": "test-only"}
            )
            self.assertEqual(completed.returncode, 0, report)
            self.assertTrue(report["readyByStage"]["research"])
            self.assertFalse(report["readyByStage"]["production"])
            self.assertEqual(
                report["checks"]["researchRoute"]["routeState"], "weread-ready"
            )
            self.assertFalse(report["checks"]["researchRoute"]["degraded"])
            self.assertEqual(report["stageStates"]["research"]["state"], "ready")

    def test_documented_research_fallback_does_not_reopen_a_completed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            case_path = project / "case.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["researchRoute"]["status"] = "unavailable-with-fallback"
            case["researchRoute"]["fallbacks"] = [
                {
                    "sourceUrl": "https://publisher.example/books/test-book",
                    "reason": "WeRead did not expose the requested edition",
                }
            ]
            write_json(case_path, case)
            completed, report = self.run_stage(project, "research")
            self.assertEqual(completed.returncode, 0, report)
            self.assertTrue(report["readyByStage"]["research"])
            self.assertFalse(report["checks"]["wereadApiKey"]["required"])
            self.assertEqual(
                report["checks"]["researchRoute"]["routeState"],
                "fallback-recorded",
            )
            self.assertTrue(report["checks"]["researchRoute"]["degraded"])
            self.assertTrue(report["checks"]["researchRoute"]["fallbackRecorded"])

    def test_missing_weread_is_degraded_and_bootstraps_a_fallback_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            completed, report = self.run_stage(project, "research")
            self.assertEqual(completed.returncode, 0, report)
            self.assertTrue(report["readyByStage"]["research"])
            route = report["checks"]["researchRoute"]
            self.assertEqual(route["routeState"], "fallback-required")
            self.assertTrue(route["degraded"])
            self.assertIn("record", route["nextAction"])
            self.assertEqual(report["stageStates"]["research"]["state"], "degraded")
            self.assertFalse(report["checks"]["wereadApiKey"]["blocking"])

    def test_malformed_declared_fallback_is_not_reported_as_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            case_path = project / "case.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["researchRoute"].update(
                {
                    "status": "unavailable-with-fallback",
                    "fallbacks": [
                        {
                            "sourceUrl": "publisher page without URL",
                            "reason": "",
                        }
                    ],
                }
            )
            write_json(case_path, case)
            completed, report = self.run_stage(project, "research")
            self.assertEqual(completed.returncode, 0, report)
            route = report["checks"]["researchRoute"]
            self.assertEqual(route["routeState"], "fallback-required")
            self.assertFalse(route["fallbackRecorded"])
            self.assertIn("sourceUrl-and-reason", route["nextAction"])

    def test_selected_pexels_route_fails_closed_without_its_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            completed, report = self.run_stage(project, "visuals")
            self.assertEqual(completed.returncode, 2, report)
            self.assertFalse(report["readyByStage"]["visuals"])
            self.assertTrue(report["checks"]["pexelsApiKey"]["required"])

    def test_local_imagegen_is_not_mislabeled_as_live_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            completed, report = self.run_stage(
                project, "visuals", {"PEXELS_API_KEY": "test-only"}
            )
            self.assertEqual(completed.returncode, 2, report)
            self.assertFalse(report["readyByStage"]["visuals"])
            self.assertTrue(report["checks"]["imagegenSkill"]["available"])
            self.assertEqual(
                report["checks"]["imagegenSkill"]["availabilityState"],
                "local-present-live-unverified",
            )
            self.assertEqual(
                report["stageStates"]["visuals"]["state"],
                "local-present-live-unverified",
            )
            self.assertTrue(
                any(
                    check["capability"] == "imagegen"
                    for check in report["requiredLiveChecks"]
                )
            )

    def test_pexels_only_route_can_finish_the_local_visual_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            case_path = project / "case.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["visualSourcePolicy"]["bodySource"] = "pexels-video"
            write_json(case_path, case)
            completed, report = self.run_stage(
                project, "visuals", {"PEXELS_API_KEY": "test-only"}
            )
            self.assertEqual(completed.returncode, 0, report)
            self.assertTrue(report["readyByStage"]["visuals"])
            self.assertEqual(report["stageStates"]["visuals"]["state"], "ready")

    def test_local_editor_route_requires_a_separate_live_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            completed, report = self.run_stage(project, "editor")
            self.assertEqual(completed.returncode, 2, report)
            self.assertFalse(report["readyByStage"]["editor"])
            editable = report["checks"]["editableDelivery"]
            self.assertEqual(editable["routeAvailabilityScope"], "local-only")
            if editable["routeAvailable"]:
                self.assertEqual(
                    report["stageStates"]["editor"]["state"],
                    "local-present-live-unverified",
                )
            self.assertTrue(
                any(
                    check["capability"] == "editable-project-write-and-readback"
                    for check in report["requiredLiveChecks"]
                )
            )

    def test_default_output_is_a_compact_actionable_stage_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = self.project(Path(temporary))
            completed, report = self.run_stage(project, "production", full=False)
            self.assertEqual(completed.returncode, 2, report)
            self.assertEqual(report["requestedStage"], "production")
            self.assertNotIn("checks", report)
            self.assertNotIn("stageStates", report)
            self.assertIn("ffmpeg", report["blockers"])
            self.assertLess(len(completed.stdout), 700, completed.stdout)
            _full, full_report = self.run_stage(project, "production")
            self.assertIn("checks", full_report)


if __name__ == "__main__":
    unittest.main()
