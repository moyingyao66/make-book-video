#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_inputs.py"
SPEC = importlib.util.spec_from_file_location("prepare_inputs", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _minimal_case():
    return {
        "book": {"title": "测试书", "authors": ["作者"]},
        "voice": {
            "resourceId": "seed-tts-2.0",
            "speaker": "test-voice",
            "enableSubtitle": True,
        },
        "segments": [
            {
                "id": "intro",
                "narration": "你好世界",
                "captions": [{"id": "c1", "zhText": "你好世界"}],
            }
        ],
    }


class ValidateCaseTests(unittest.TestCase):
    def test_valid_case_passes(self):
        self.assertEqual(MODULE.validate_case(_minimal_case()), [])

    def test_empty_title_fails(self):
        case = _minimal_case()
        case["book"]["title"] = ""
        errors = MODULE.validate_case(case)
        self.assertTrue(any("book.title" in e for e in errors))

    def test_missing_narration_fails(self):
        case = _minimal_case()
        case["segments"][0]["narration"] = ""
        errors = MODULE.validate_case(case)
        self.assertTrue(any("narration" in e for e in errors))

    def test_text_mismatch_fails(self):
        case = _minimal_case()
        case["segments"][0]["captions"][0]["zhText"] = "你好"
        errors = MODULE.validate_case(case)
        self.assertTrue(any("mismatch" in e for e in errors))

    def test_duplicate_segment_id_fails(self):
        case = _minimal_case()
        case["segments"].append(
            {
                "id": "intro",
                "narration": "重复",
                "captions": [{"id": "c2", "zhText": "重复"}],
            }
        )
        errors = MODULE.validate_case(case)
        self.assertTrue(any("duplicated" in e for e in errors))

    def test_narration_text_generation(self):
        case = _minimal_case()
        case["segments"].append(
            {
                "id": "body",
                "narration": "第二段",
                "captions": [{"id": "c2", "zhText": "第二段"}],
            }
        )
        text = MODULE.generate_narration_text(case)
        self.assertEqual(text, "你好世界\n第二段")

    def test_hold_references_unknown_segment(self):
        case = _minimal_case()
        case["timelineHolds"] = [
            {"id": "h1", "afterSegmentId": "nonexistent", "durationFrames": 30}
        ]
        errors = MODULE.validate_case(case)
        self.assertTrue(any("nonexistent" in e for e in errors))

    def test_subtitle_disabled_fails(self):
        case = _minimal_case()
        case["voice"]["enableSubtitle"] = False
        errors = MODULE.validate_case(case)
        self.assertTrue(any("enableSubtitle" in e for e in errors))

    def test_spoken_text_alias(self):
        case = _minimal_case()
        case["segments"][0]["narration"] = ""
        case["segments"][0]["spoken_text"] = "你好世界"
        errors = MODULE.validate_case(case)
        self.assertEqual(errors, [])

    def test_empty_segments_fails(self):
        case = _minimal_case()
        case["segments"] = []
        errors = MODULE.validate_case(case)
        self.assertTrue(any("segments is empty" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
