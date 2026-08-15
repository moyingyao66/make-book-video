#!/usr/bin/env python3

import array
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_timestamp_timeline.py"
SPEC = importlib.util.spec_from_file_location("build_timestamp_timeline", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AcousticHoldTests(unittest.TestCase):
    def test_selects_center_of_longest_verified_silence(self) -> None:
        samples = array.array("h", [4000] * 500 + [0] * 400 + [4000] * 500)
        evidence = MODULE.find_safe_pcm_silence(
            samples.tobytes(),
            channels=1,
            sample_rate=1000,
            search_start_ms=0,
            search_end_ms=1400,
        )
        self.assertEqual(evidence["boundaryMethod"], "verified-pcm-silence")
        self.assertEqual(evidence["rawBoundaryMs"], 700.0)
        self.assertEqual(evidence["silenceDurationMs"], 400.0)
        self.assertLessEqual(
            evidence["guardRmsDbfs"], evidence["silenceThresholdDbfs"]
        )

    def test_fails_when_no_safe_silence_exists(self) -> None:
        samples = array.array("h", [4000] * 1000)
        with self.assertRaises(SystemExit):
            MODULE.find_safe_pcm_silence(
                samples.tobytes(),
                channels=1,
                sample_rate=1000,
                search_start_ms=0,
                search_end_ms=1000,
            )

    def test_rejects_a_caption_boundary_inside_one_provider_item(self) -> None:
        timed = [
            {"providerWordKey": "word-0001"},
            {"providerWordKey": "word-0001"},
            {"providerWordKey": "word-0002"},
        ]
        with self.assertRaises(SystemExit):
            MODULE.require_provider_item_boundary(timed, 1, "caption")

    def test_accepts_a_boundary_between_provider_items(self) -> None:
        timed = [
            {"providerWordKey": "word-0001"},
            {"providerWordKey": "word-0002"},
        ]
        MODULE.require_provider_item_boundary(timed, 1, "caption")

    def test_ass_uses_configured_canvas_font_and_position(self) -> None:
        ass = MODULE.build_ass(
            [{"zhText": "甲", "enText": "A", "startFrame": 0, "endFrame": 30}],
            30,
            width=720,
            height=1280,
            font="Noto Sans CJK SC",
            font_size=42,
            english_font_size=24,
            position_y=1160,
        )
        self.assertIn("PlayResX: 720", ass)
        self.assertIn("Style: Caption,Noto Sans CJK SC,42", ass)
        self.assertIn(r"{\an2\pos(360,1160)}甲", ass)
        self.assertIn(r"{\fs24\b0}\NA", ass)


if __name__ == "__main__":
    unittest.main()
