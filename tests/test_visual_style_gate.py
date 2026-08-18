#!/usr/bin/env python3
"""One project must generate every scene under one frozen house style."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_case import validate_visual_source_policy  # noqa: E402

TEMPLATE_POLICY = json.loads(
    (ROOT / "assets/case-template.json").read_text(encoding="utf-8")
)["visualSourcePolicy"]
TEMPLATE_STYLE = TEMPLATE_POLICY["visualStyle"]
TEMPLATE_PLAN = TEMPLATE_POLICY["visualPlan"]


def pexels_plan() -> dict:
    plan = json.loads(json.dumps(TEMPLATE_PLAN))
    for group in plan["groups"]:
        group["path"] = f"assets/pexels/{group['assetId']}.mp4"
    return plan


def policy(**overrides) -> dict:
    document = {
        "version": 3,
        "visualSourcePolicy": {
            "selectionStatus": "confirmed",
            "selectionMethod": "host-structured-choice",
            "selectedAtProjectStart": True,
            "openingSource": "pexels-video",
            "bodySource": "gpt-image",
            "silentFallbackAllowed": False,
            "visualStyle": json.loads(json.dumps(TEMPLATE_STYLE)),
            "visualPlan": json.loads(json.dumps(TEMPLATE_PLAN)),
        },
    }
    document["visualSourcePolicy"].update(overrides)
    return document


class VisualStyleGateTests(unittest.TestCase):
    def test_template_style_satisfies_the_gate(self) -> None:
        self.assertEqual(validate_visual_source_policy(policy()), [])

    def test_generated_route_requires_a_style(self) -> None:
        errors = validate_visual_source_policy(policy(visualStyle=None))
        self.assertIn(
            "visualSourcePolicy.visualStyle is required for a gpt-image route", errors
        )

    def test_unfrozen_or_thin_style_is_rejected(self) -> None:
        style = json.loads(json.dumps(TEMPLATE_STYLE))
        style["frozen"] = False
        style["promptContract"] = "随便画"
        style["forbidden"] = []
        errors = validate_visual_source_policy(policy(visualStyle=style))
        self.assertIn("visualStyle.frozen must be true before generating any scene", errors)
        self.assertTrue(any("promptContract" in error for error in errors), errors)
        self.assertTrue(any("forbidden" in error for error in errors), errors)

    def test_pexels_only_project_does_not_need_a_generated_style(self) -> None:
        document = policy(
            bodySource="pexels-video", visualStyle=None, visualPlan=pexels_plan()
        )
        self.assertEqual(validate_visual_source_policy(document), [])

    def test_initializer_freezes_the_style_in_new_projects(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "book"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "init_case.py"),
                    str(project),
                    "--title",
                    "测试",
                    "--author",
                    "作者",
                    "--opening-source",
                    "pexels-video",
                    "--body-source",
                    "gpt-image",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            case = json.loads((project / "case.json").read_text(encoding="utf-8"))
            style = case["visualSourcePolicy"]["visualStyle"]
            self.assertTrue(style["frozen"])
            self.assertEqual(style["profileId"], TEMPLATE_STYLE["profileId"])
            self.assertIn("字幕安全区", style["promptContract"])

    def test_plan_must_cover_every_body_role_once_in_order(self) -> None:
        plan = json.loads(json.dumps(TEMPLATE_PLAN))
        plan["groups"][1]["segments"] = ["concrete-example", "alternative-explanation"]
        errors = validate_visual_source_policy(policy(visualPlan=plan))
        self.assertTrue(any("narrative order" in error for error in errors), errors)

    def test_plan_count_must_match_the_groups(self) -> None:
        plan = json.loads(json.dumps(TEMPLATE_PLAN))
        plan["bodyVisualCount"] = 5
        errors = validate_visual_source_policy(policy(visualPlan=plan))
        self.assertIn(
            "visualPlan.groups must contain exactly bodyVisualCount entries", errors
        )

    def test_plan_paths_follow_the_selected_body_source(self) -> None:
        errors = validate_visual_source_policy(
            policy(bodySource="pexels-video", visualStyle=None)
        )
        self.assertTrue(any("assets/pexels/" in error for error in errors), errors)

    def test_missing_plan_is_rejected(self) -> None:
        errors = validate_visual_source_policy(policy(visualPlan=None))
        self.assertIn("visualSourcePolicy.visualPlan is required", errors)


if __name__ == "__main__":
    unittest.main()
