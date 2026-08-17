#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_timestamp_timeline.py"
SPEC = importlib.util.spec_from_file_location("build_timestamp_timeline", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AssTimeTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(MODULE.ass_time(0, 30), "0:00:00.00")

    def test_one_frame(self):
        self.assertEqual(MODULE.ass_time(1, 30), "0:00:00.03")

    def test_one_second(self):
        self.assertEqual(MODULE.ass_time(30, 30), "0:00:01.00")

    def test_one_minute(self):
        self.assertEqual(MODULE.ass_time(30 * 60, 30), "0:01:00.00")

    def test_one_hour(self):
        self.assertEqual(MODULE.ass_time(30 * 3600, 30), "1:00:00.00")

    def test_59_seconds_last_frame(self):
        result = MODULE.ass_time(30 * 59 + 29, 30)
        self.assertEqual(result, "0:00:59.97")

    def test_centisecond_carry_at_unusual_fps(self):
        # fps=200, frame=11999: 59.995s → old code would produce "0:00:60.00"
        self.assertEqual(MODULE.ass_time(11999, 200), "0:01:00.00")

    def test_25fps(self):
        self.assertEqual(MODULE.ass_time(25, 25), "0:00:01.00")
        self.assertEqual(MODULE.ass_time(50, 25), "0:00:02.00")

    def test_no_illegal_seconds_at_boundaries(self):
        fps = 30
        for minute in range(0, 65):
            base = minute * 60 * fps
            for offset in range(-fps, fps + 1):
                frame = base + offset
                if frame < 0:
                    continue
                result = MODULE.ass_time(frame, fps)
                parts = result.split(":")
                ss = int(parts[2].split(".")[0])
                mm = int(parts[1])
                self.assertLess(ss, 60, f"Illegal seconds at frame {frame}: {result}")
                self.assertLess(mm, 60, f"Illegal minutes at frame {frame}: {result}")


if __name__ == "__main__":
    unittest.main()
