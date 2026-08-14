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


if __name__ == "__main__":
    unittest.main()
