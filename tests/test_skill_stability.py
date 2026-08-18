#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from score_trigger_evals import (  # noqa: E402
    load_json,
    result_template,
    score_results,
    validate_suite,
)
from score_execution_evals import (  # noqa: E402
    bind_declared_assertions,
    declared_assertions_for_stage,
    final_media_qa_errors,
    rendered_artifact_errors,
)
from tests.test_copy_contract import version_three_visual_fixture  # noqa: E402


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_trigger_observations(suite: dict) -> dict:
    observations = result_template(suite)
    observations.update(
        {
            "targetHost": "Codex Desktop",
            "targetHostVersion": "2026.08.17+build.4312",
            "evaluationDate": date.today().isoformat(),
        }
    )
    cases = {item["id"]: item for item in suite["triggerCases"]}
    runs = suite["runsPerPrompt"]
    for item in observations["results"]:
        case = cases[item["id"]]
        use_skill = case["expect"] == "use"
        item["triggered"] = [use_skill] * runs
        route = "make-book-video" if use_skill else case["expectedRoute"]
        item["selectedSkill"] = [route] * runs
    return observations


def materialize_trigger_evidence(observations: dict, evidence_root: Path) -> None:
    """Write one immutable-looking test envelope for every summarized host run."""

    for item in observations["results"]:
        case_id = item["id"]
        item["runEvidence"] = []
        for run_index, (triggered, selected_skill) in enumerate(
            zip(item["triggered"], item["selectedSkill"]), start=1
        ):
            session_id = f"session-{case_id}-{run_index}"
            relative_path = Path("run-records") / case_id / f"run-{run_index}.json"
            record_path = evidence_root / relative_path
            write_json(
                record_path,
                {
                    "caseId": case_id,
                    "runIndex": run_index,
                    "sessionId": session_id,
                    "triggered": triggered,
                    "selectedSkill": selected_skill,
                    "hostTrace": {"fixtureOnly": True},
                },
            )
            item["runEvidence"].append(
                {
                    "sessionId": session_id,
                    "recordPath": relative_path.as_posix(),
                    "recordSha256": sha256(record_path),
                }
            )


def score_with_test_evidence(
    suite: dict, observations: dict
) -> tuple[dict, list[str]]:
    with tempfile.TemporaryDirectory() as temporary:
        evidence_root = Path(temporary)
        materialize_trigger_evidence(observations, evidence_root)
        return score_results(suite, observations, evidence_root=evidence_root)


class SkillStructureTests(unittest.TestCase):
    def test_frontmatter_and_main_body_stay_within_context_budget(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        _, frontmatter, body = text.split("---", 2)
        description_line = next(
            line for line in frontmatter.splitlines() if line.startswith("description:")
        )
        description = json.loads(description_line.split(":", 1)[1].strip())
        self.assertLessEqual(len(description), 1024)
        self.assertLessEqual(len(body.strip().splitlines()), 500)

    def test_every_linked_reference_exists(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        references = set(re.findall(r"\[[^\]]+\]\((references/[^)#]+)\)", text))
        self.assertGreaterEqual(len(references), 6)
        missing = sorted(value for value in references if not (ROOT / value).is_file())
        self.assertEqual(missing, [])

    def test_production_workflow_is_linked_and_keeps_default_film_order(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/production-workflow.md", skill)
        workflow = (ROOT / "references/production-workflow.md").read_text(
            encoding="utf-8"
        )
        beats = (
            "`fixed-opening`",
            "`anticipation-carousel`",
            "`book-reveal`",
            "`audience-problem`",
            "`alternative-explanation`",
            "`concrete-example`",
            "`practical-boundary`",
            "`audience-close`",
        )
        positions = [workflow.index(beat) for beat in beats]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("only text is `《书名》` and `作者`", workflow)
        self.assertIn("exactly one Doubao Seed TTS 2.0 V3 request", workflow)

    def test_visual_contract_is_copy_first_faceless_simple_and_editable(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        visuals = (ROOT / "references/visuals.md").read_text(encoding="utf-8")
        profiles = (ROOT / "references/visual-style-profiles.md").read_text(
            encoding="utf-8"
        )
        schema = (ROOT / "references/project-schema.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Treat the approved narration as the creative spine", skill)
        self.assertIn("exactly three book-appropriate preview styles", skill)
        self.assertIn("avoid-recognizable-faces", skill)
        self.assertIn("12–18 independently timed segment entries", visuals)
        self.assertIn("There is no universal “most popular” profile", profiles)
        self.assertIn("without a flattened multi-panel container", schema)

    def test_long_references_have_a_contents_section(self) -> None:
        for path in sorted((ROOT / "references").glob("*.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) >= 100:
                self.assertIn("## Contents", lines, path.name)


class TriggerEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = load_json(ROOT / "evals/skill-evals.json")

    def test_suite_has_balanced_repeated_hard_cases(self) -> None:
        self.assertEqual(validate_suite(self.suite), [])
        expectations = [item["expect"] for item in self.suite["triggerCases"]]
        self.assertEqual(expectations.count("use"), 10)
        self.assertEqual(expectations.count("skip"), 10)
        self.assertEqual(self.suite["runsPerPrompt"], 3)
        self.assertEqual(self.suite["thresholds"]["minimumUseCaseSuccessRate"], 1.0)
        self.assertEqual(self.suite["thresholds"]["minimumExpectedRouteRate"], 1.0)
        self.assertEqual(self.suite["thresholds"]["minimumCaseStabilityRate"], 1.0)
        self.assertTrue(
            all(
                item.get("expectedRoute")
                for item in self.suite["triggerCases"]
                if item["expect"] == "skip"
            )
        )
        implicit_ids = {
            "use-title-first-later-image-swap",
            "use-book-page-recurring-cover-swap",
            "use-title-later-opening-caption-edit",
        }
        implicit_prompts = [
            item["prompt"]
            for item in self.suite["triggerCases"]
            if item["id"] in implicit_ids
        ]
        self.assertEqual(len(implicit_prompts), 3)
        for prompt in implicit_prompts:
            self.assertFalse(
                any(
                    token.lower() in prompt.lower()
                    for token in (
                        "make-book-video",
                        "chatcut",
                        "工程",
                        "可编辑",
                        "可剪辑",
                        "双交付",
                        "mp4",
                    )
                ),
                prompt,
            )

    def test_suite_rejects_missing_route_wrong_size_and_missing_stage(self) -> None:
        missing_route = copy.deepcopy(self.suite)
        missing_route["triggerCases"][10].pop("expectedRoute")
        self.assertTrue(
            any("expectedRoute" in error for error in validate_suite(missing_route))
        )

        wrong_size = copy.deepcopy(self.suite)
        wrong_size["triggerCases"].pop(0)
        self.assertTrue(
            any("exactly 10" in error for error in validate_suite(wrong_size))
        )

        missing_stage = copy.deepcopy(self.suite)
        missing_stage["executionAssertions"][0].pop("stage")
        self.assertTrue(
            any("invalid stage" in error for error in validate_suite(missing_stage))
        )

    def test_perfect_observations_pass_and_one_unstable_case_is_visible(self) -> None:
        observations = complete_trigger_observations(self.suite)
        report, errors = score_with_test_evidence(self.suite, observations)
        self.assertEqual(errors, [])
        self.assertTrue(report["ok"], report)

        unstable_observations = copy.deepcopy(observations)
        unstable_observations["results"][0]["triggered"] = [True, False, True]
        unstable_observations["results"][0]["selectedSkill"] = [
            "make-book-video",
            "none",
            "make-book-video",
        ]
        unstable, errors = score_with_test_evidence(
            self.suite, unstable_observations
        )
        self.assertEqual(errors, [])
        self.assertFalse(unstable["perCase"][0]["stable"])
        self.assertLess(unstable["caseStabilityRate"], 1.0)
        self.assertFalse(unstable["ok"])

        wrong_route_observations = copy.deepcopy(observations)
        skip_item = next(
            item
            for item in wrong_route_observations["results"]
            if item["id"] == "skip-concept-explainer"
        )
        skip_item["selectedSkill"] = ["writing"] * 3
        wrong_route, errors = score_with_test_evidence(
            self.suite, wrong_route_observations
        )
        self.assertEqual(errors, [])
        self.assertLess(wrong_route["expectedRouteRate"], 1.0)
        self.assertFalse(wrong_route["ok"])

        route_unstable_observations = copy.deepcopy(observations)
        skip_item = next(
            item
            for item in route_unstable_observations["results"]
            if item["id"] == "skip-concept-explainer"
        )
        skip_item["selectedSkill"] = [
            "faceless-explainer",
            "writing",
            "faceless-explainer",
        ]
        route_unstable, errors = score_with_test_evidence(
            self.suite, route_unstable_observations
        )
        self.assertEqual(errors, [])
        route_case = next(
            item
            for item in route_unstable["perCase"]
            if item["id"] == "skip-concept-explainer"
        )
        self.assertFalse(route_case["stable"])
        self.assertFalse(route_unstable["ok"])

    def test_one_consistently_failed_use_case_cannot_hide_in_aggregate(self) -> None:
        observations = complete_trigger_observations(self.suite)
        failed = observations["results"][0]
        failed["triggered"] = [False, False, False]
        failed["selectedSkill"] = ["none", "none", "none"]

        report, errors = score_with_test_evidence(self.suite, observations)

        self.assertEqual(errors, [])
        self.assertEqual(
            report["shouldTriggerRate"],
            self.suite["thresholds"]["minimumShouldTriggerRate"],
        )
        self.assertEqual(report["minimumUseCaseSuccessRate"], 0.0)
        self.assertTrue(report["perCase"][0]["stable"])
        self.assertFalse(report["ok"])

    def test_results_require_real_run_metadata_and_exact_case_ids(self) -> None:
        observations = complete_trigger_observations(self.suite)
        observations["targetHostVersion"] = ""
        observations["evaluationDate"] = "not-a-date"
        observations["suiteSha256"] = "stale"
        _, errors = score_with_test_evidence(self.suite, observations)
        self.assertTrue(any("targetHostVersion" in error for error in errors))
        self.assertTrue(any("evaluationDate" in error for error in errors))
        self.assertTrue(any("suiteSha256" in error for error in errors))

        duplicate = complete_trigger_observations(self.suite)
        duplicate["results"].append(copy.deepcopy(duplicate["results"][0]))
        _, errors = score_with_test_evidence(self.suite, duplicate)
        self.assertTrue(any("duplicate result id" in error for error in errors))

        extra = complete_trigger_observations(self.suite)
        extra["results"].append(
            {
                "id": "not-in-suite",
                "triggered": [False, False, False],
                "selectedSkill": ["none", "none", "none"],
            }
        )
        _, errors = score_with_test_evidence(self.suite, extra)
        self.assertTrue(any("unexpected result" in error for error in errors))

    def test_results_reject_placeholder_version_and_future_date(self) -> None:
        for placeholder in ("latest", "fixture-build-4312", "test-2026.08.17"):
            with self.subTest(placeholder=placeholder):
                observations = complete_trigger_observations(self.suite)
                observations["targetHostVersion"] = placeholder
                observations["evaluationDate"] = (
                    date.today() + timedelta(days=1)
                ).isoformat()

                _, errors = score_with_test_evidence(self.suite, observations)

                self.assertTrue(
                    any("reproducible build identifier" in error for error in errors)
                )
                self.assertTrue(
                    any("cannot be in the future" in error for error in errors)
                )

    def test_every_run_requires_unique_in_bounds_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary)
            observations = complete_trigger_observations(self.suite)
            materialize_trigger_evidence(observations, evidence_root)
            all_evidence = [
                evidence
                for item in observations["results"]
                for evidence in item["runEvidence"]
            ]
            self.assertEqual(len(all_evidence), 60)
            self.assertEqual(
                len({item["sessionId"] for item in all_evidence}), 60
            )
            self.assertEqual(
                len({item["recordPath"] for item in all_evidence}), 60
            )
            report, errors = score_results(
                self.suite, observations, evidence_root=evidence_root
            )
            self.assertEqual(errors, [])
            self.assertTrue(report["ok"])

            first, second = all_evidence[:2]
            second["sessionId"] = first["sessionId"]
            second["recordPath"] = first["recordPath"]
            second["recordSha256"] = first["recordSha256"]
            _, errors = score_results(
                self.suite, observations, evidence_root=evidence_root
            )
            self.assertTrue(any("duplicate trigger evidence sessionId" in error for error in errors))
            self.assertTrue(any("duplicate trigger evidence recordPath" in error for error in errors))

            observations = complete_trigger_observations(self.suite)
            materialize_trigger_evidence(observations, evidence_root)
            escaping = observations["results"][0]["runEvidence"][0]
            escaping["recordPath"] = "../outside.json"
            _, errors = score_results(
                self.suite, observations, evidence_root=evidence_root
            )
            self.assertTrue(any("relative JSON path" in error for error in errors))

    def test_evidence_record_fields_and_hash_must_match_summary(self) -> None:
        mutations = (
            ("caseId", "wrong-case", "caseId differs"),
            ("runIndex", 99, "runIndex differs"),
            ("sessionId", "wrong-session", "sessionId differs"),
            ("triggered", False, "triggered value differs"),
            ("selectedSkill", "none", "selectedSkill differs"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                evidence_root = Path(temporary)
                observations = complete_trigger_observations(self.suite)
                materialize_trigger_evidence(observations, evidence_root)
                evidence = observations["results"][0]["runEvidence"][0]
                record_path = evidence_root / evidence["recordPath"]
                record = json.loads(record_path.read_text(encoding="utf-8"))
                record[field] = value
                write_json(record_path, record)
                evidence["recordSha256"] = sha256(record_path)

                _, errors = score_results(
                    self.suite, observations, evidence_root=evidence_root
                )

                self.assertTrue(
                    any(expected_error in error for error in errors), errors
                )

        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary)
            observations = complete_trigger_observations(self.suite)
            materialize_trigger_evidence(observations, evidence_root)
            evidence = observations["results"][0]["runEvidence"][0]
            record_path = evidence_root / evidence["recordPath"]
            record_path.write_text("{}\n", encoding="utf-8")
            _, errors = score_results(
                self.suite, observations, evidence_root=evidence_root
            )
            self.assertTrue(any("recordSha256 is stale" in error for error in errors))

            record_path.unlink()
            _, errors = score_results(
                self.suite, observations, evidence_root=evidence_root
            )
            self.assertTrue(any("evidence record is missing" in error for error in errors))

    def test_scoring_cannot_pass_without_opening_evidence_records(self) -> None:
        observations = complete_trigger_observations(self.suite)
        for item in observations["results"]:
            item["runEvidence"] = [
                {
                    "sessionId": f"session-{item['id']}-{run_index}",
                    "recordPath": f"run-records/{item['id']}-{run_index}.json",
                    "recordSha256": "0" * 64,
                }
                for run_index in range(1, 4)
            ]

        report, errors = score_results(self.suite, observations)

        self.assertFalse(report["ok"])
        self.assertTrue(any("evidence root is required" in error for error in errors))


class ExecutionEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = load_json(ROOT / "evals/skill-evals.json")

    def test_declared_assertions_match_every_stage(self) -> None:
        expected = {
            "draft": {"startup-policy", "draft-contract", "approval-output"},
            "synthesis": {
                "startup-policy",
                "draft-contract",
                "approval-output",
                "approval-receipt",
            },
            "render": {
                "startup-policy",
                "draft-contract",
                "approval-output",
                "approval-receipt",
                "render-assets",
                "provider-timestamps",
                "rendered-artifacts",
            },
            "release": {
                "startup-policy",
                "draft-contract",
                "approval-output",
                "approval-receipt",
                "render-assets",
                "provider-timestamps",
                "rendered-artifacts",
                "editor-plan",
                "editable-delivery",
                "final-media-qa",
                "release-freshness",
            },
        }
        for stage, gate_ids in expected.items():
            declared = declared_assertions_for_stage(self.suite, stage)
            self.assertEqual(set(declared), gate_ids)
            gates = [{"id": gate_id} for gate_id in gate_ids]
            self.assertEqual(
                set(bind_declared_assertions(gates, self.suite, stage)), gate_ids
            )

        missing = copy.deepcopy(self.suite)
        missing["executionAssertions"] = [
            item
            for item in missing["executionAssertions"]
            if item["id"] != "final-media-qa"
        ]
        gates = [{"id": gate_id} for gate_id in expected["release"]]
        with self.assertRaisesRegex(ValueError, "undeclared"):
            bind_declared_assertions(gates, missing, "release")

    def test_rendered_artifacts_bind_audio_mix_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            paths = {
                "video": project / "renders/video.mp4",
                "case": project / "case.json",
                "manifest": project / "render-manifest.json",
                "alignment": project / "timing/alignment-report.json",
                "captions": project / "timing/caption-timeline.json",
                "scenes": project / "timing/scene-timeline.json",
                "subtitles": project / "timing/subtitles.ass",
                "narration": project / "timing/narration.timestamped.final.wav",
                "rawNarration": project / "audio/narration.raw.wav",
                "ttsReport": project / "audio/narration.raw.wav.json",
                "wordTimeline": project / "timing/word-timeline.json",
                "audio": project / "renders/audio_mix.m4a",
            }
            for name, path in paths.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"{name}-fixture".encode("utf-8"))
            build = {
                "video": "renders/video.mp4",
                "videoSha256": sha256(paths["video"]),
                "caseSha256": sha256(paths["case"]),
                "renderManifestSha256": sha256(paths["manifest"]),
                "alignmentReport": "timing/alignment-report.json",
                "alignmentReportSha256": sha256(paths["alignment"]),
                "captionTimeline": "timing/caption-timeline.json",
                "captionTimelineSha256": sha256(paths["captions"]),
                "sceneTimeline": "timing/scene-timeline.json",
                "sceneTimelineSha256": sha256(paths["scenes"]),
                "subtitleFile": "timing/subtitles.ass",
                "subtitleSha256": sha256(paths["subtitles"]),
                "narrationAudio": "timing/narration.timestamped.final.wav",
                "narrationAudioSha256": sha256(paths["narration"]),
                "rawNarrationAudio": "audio/narration.raw.wav",
                "rawNarrationAudioSha256": sha256(paths["rawNarration"]),
                "ttsReport": "audio/narration.raw.wav.json",
                "ttsReportSha256": sha256(paths["ttsReport"]),
                "wordTimeline": "timing/word-timeline.json",
                "wordTimelineSha256": sha256(paths["wordTimeline"]),
                "audioMix": "renders/audio_mix.m4a",
                "audioMixSha256": sha256(paths["audio"]),
            }
            write_json(project / "build_report.json", build)
            self.assertEqual(rendered_artifact_errors(project), [])

            paths["audio"].write_bytes(b"changed-audio")
            errors = rendered_artifact_errors(project)
            self.assertTrue(any("audioMixSha256" in error for error in errors))

    def test_final_media_qa_binds_packet_and_mix_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            video = project / "renders/video.mp4"
            audio_mix = project / "renders/audio_mix.m4a"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video-fixture")
            audio_mix.write_bytes(b"audio-fixture")
            report_path = project / "renders/qa/qa-report.json"
            write_json(
                report_path,
                {
                    "ok": True,
                    "structuralOk": True,
                    "decodePassed": True,
                    "failures": [],
                    "video": {"sha256": sha256(video)},
                    "audio": {
                        "packetHashMatches": True,
                        "mix": "renders/audio_mix.m4a",
                        "mixSha256": sha256(audio_mix),
                    },
                    "editableDelivery": {"ok": True},
                    "visualReview": {"passed": True},
                    "providerTiming": {"ok": True, "failures": []},
                },
            )
            self.assertEqual(final_media_qa_errors(project), [])

            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["audio"]["packetHashMatches"] = False
            write_json(report_path, report)
            self.assertTrue(
                any(
                    "packetHashMatches" in error
                    for error in final_media_qa_errors(project)
                )
            )

            report["audio"]["packetHashMatches"] = True
            write_json(report_path, report)
            audio_mix.write_bytes(b"changed-audio")
            self.assertTrue(
                any(
                    "audio mix hash" in error
                    for error in final_media_qa_errors(project)
                )
            )


class ApprovalOutputTests(unittest.TestCase):
    def test_approval_package_is_reproducible_and_contains_full_narration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            case, manifest = version_three_visual_fixture()
            case["status"] = "draft"
            case["approval"] = {
                "contentApprovedByUser": False,
                "storyboardApprovedByUser": False,
                "paidGenerationAuthorized": False,
            }
            manifest["canvas"] = case["canvas"]
            manifest["captions"] = {
                "mode": "zh-only",
                "requireEnglish": False,
                "fontSize": 72,
                "englishFontSize": 40,
                "positionY": 1500,
                "safeBottomPx": 360,
            }
            write_json(project / "case.json", case)
            write_json(project / "render-manifest.json", manifest)
            command = [
                sys.executable,
                str(SCRIPTS / "build_approval_package.py"),
                str(project),
            ]
            first = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            json_bytes = (project / "approval-package.json").read_bytes()
            markdown_bytes = (project / "approval-package.md").read_bytes()

            second = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(json_bytes, (project / "approval-package.json").read_bytes())
            self.assertEqual(markdown_bytes, (project / "approval-package.md").read_bytes())

            package = json.loads(json_bytes)
            expected = "\n".join(item["narration"] for item in case["segments"])
            self.assertEqual(package["narration"]["fullText"], expected)
            markdown = markdown_bytes.decode("utf-8")
            self.assertIn("## 完整旁白", markdown)
            self.assertIn(expected, markdown)
            self.assertIn("## 证据边界", markdown)
            self.assertIn("## 语义分镜", markdown)

            score_command = [
                sys.executable,
                str(SCRIPTS / "score_execution_evals.py"),
                str(project),
                "--stage",
                "draft",
            ]
            score = subprocess.run(
                score_command, capture_output=True, text=True, check=False
            )
            score_report = json.loads(score.stdout)
            self.assertEqual(score.returncode, 0, score_report)
            self.assertEqual(score_report["gatePassRate"], 1.0)
            self.assertEqual(score_report["passedGates"], score_report["totalGates"])

            case["angle"] = "changed after approval package"
            write_json(project / "case.json", case)
            stale = subprocess.run(
                score_command, capture_output=True, text=True, check=False
            )
            stale_report = json.loads(stale.stdout)
            self.assertEqual(stale.returncode, 2, stale_report)
            approval_gate = next(
                item
                for item in stale_report["gates"]
                if item["id"] == "approval-output"
            )
            self.assertFalse(approval_gate["passed"])


if __name__ == "__main__":
    unittest.main()
