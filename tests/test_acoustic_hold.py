#!/usr/bin/env python3

from __future__ import annotations

import array
import copy
import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_timestamp_timeline.py"
SPEC = importlib.util.spec_from_file_location("build_timestamp_timeline", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AcousticHoldTests(unittest.TestCase):
    def provider_fixture(self, root: Path) -> tuple[Path, dict, dict]:
        audio = root / "raw.wav"
        with wave.open(str(audio), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(24000)
            target.writeframes(b"\x00\x00" * 24000)
        case = {
            "voice": {
                "resourceId": "seed-tts-2.0",
                "speaker": "test-speaker",
                "speechRate": 20,
                "enableSubtitle": True,
                "requireSingleProviderRequest": True,
            },
            "segments": [{"id": "one", "narration": "甲"}],
        }
        report = {
            "provider": "doubao-direct-v3",
            "status": "verified-provider-word-timestamps",
            "audioSha256": MODULE.sha256(audio),
            "audioDurationMs": 1000.0,
            "sampleRate": 24000,
            "channels": 1,
            "sampleWidthBytes": 2,
            "resourceId": "seed-tts-2.0",
            "speaker": "test-speaker",
            "speechRate": 20,
            "enableSubtitle": True,
            "requestMode": "single",
            "providerRequestCount": 1,
            "providerAttemptCount": 1,
            "xTtLogids": ["log-1"],
            "providerRequests": [
                {
                    "requestId": "request-1",
                    "xTtLogid": "log-1",
                    "httpStatus": 200,
                    "attemptCount": 1,
                    "attempts": [
                        {
                            "attempt": 1,
                            "requestId": "request-1",
                            "xTtLogid": "log-1",
                            "status": "succeeded",
                            "httpStatus": 200,
                        }
                    ],
                    "wordCount": 1,
                }
            ],
            "timestamps": {
                "source": "Doubao V3 sentence.words",
                "count": 1,
                "words": [
                    {
                        "key": "word-0001",
                        "word": "甲",
                        "startMs": 0.0,
                        "endMs": 500.0,
                        "confidence": None,
                        "requestIndex": 1,
                    }
                ],
            },
        }
        return audio, case, report

    def test_provider_evidence_reconciles_report_audio_voice_and_words(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio, case, report = self.provider_fixture(Path(temporary))
            evidence = MODULE.validate_provider_evidence(report, audio, case)
            self.assertEqual(evidence["timedChars"][0]["char"], "甲")

    def test_provider_evidence_rejects_each_unbound_provider_field(self) -> None:
        mutations = {
            "provider": lambda value: value.update({"provider": "other"}),
            "audio hash": lambda value: value.update({"audioSha256": "0" * 64}),
            "resource": lambda value: value.update({"resourceId": "other"}),
            "speaker": lambda value: value.update({"speaker": "other"}),
            "rate": lambda value: value.update({"speechRate": 21}),
            "subtitle": lambda value: value.update({"enableSubtitle": False}),
            "mode": lambda value: value.update({"requestMode": "chunked"}),
            "request count": lambda value: value.update({"providerRequestCount": 2}),
            "attempt count": lambda value: value.update({"providerAttemptCount": 2}),
            "log id": lambda value: value.update({"xTtLogids": ["other"]}),
            "request http": lambda value: value["providerRequests"][0].update(
                {"httpStatus": 201}
            ),
            "attempt http": lambda value: value["providerRequests"][0]["attempts"][
                0
            ].update({"httpStatus": 500}),
            "word count": lambda value: value["providerRequests"][0].update(
                {"wordCount": 2}
            ),
            "missing key": lambda value: value["timestamps"]["words"][0].update(
                {"key": ""}
            ),
            "out-of-order key": lambda value: value["timestamps"]["words"][0].update(
                {"key": "word-0002"}
            ),
            "words": lambda value: value["timestamps"]["words"][0].update(
                {"word": "乙"}
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            audio, case, report = self.provider_fixture(Path(temporary))
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    changed = copy.deepcopy(report)
                    mutate(changed)
                    with self.assertRaises(SystemExit):
                        MODULE.validate_provider_evidence(changed, audio, case)

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

    def test_ass_wraps_long_chinese_and_english_before_rendering(self) -> None:
        chinese = "入职后才发现薪资成长空间和工作方式几乎都没认真比较"
        english = "Only after joining do you realize you barely compared pay, growth, or work style."
        self.assertTrue(
            all(len(line) <= 12 for line in MODULE.wrap_chinese_caption(chinese, 12))
        )
        self.assertGreater(len(MODULE.wrap_english_caption(english, 38)), 1)
        orphan_case = MODULE.wrap_chinese_caption(
            "当场就觉得这份工作适合自己。", 12
        )
        self.assertGreaterEqual(len(orphan_case[-1]), 6)
        ass = MODULE.build_ass(
            [{"zhText": chinese, "enText": english, "startFrame": 0, "endFrame": 30}],
            30,
        )
        dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))
        self.assertGreaterEqual(dialogue.count(r"\N"), 3)

    def test_non_integer_audio_frame_tail_is_assigned_to_last_narrated_scene(self) -> None:
        scenes = [
            {
                "id": "intro",
                "kind": "narrated",
                "startFrame": 0,
                "endFrame": 10,
            },
            {
                "id": "hold",
                "kind": "silent-hold",
                "startFrame": 10,
                "endFrame": 15,
            },
            {
                "id": "body",
                "kind": "narrated",
                "startFrame": 15,
                "endFrame": 30,
            },
        ]
        captions = [
            {"id": "c1", "segmentId": "intro", "startFrame": 0, "endFrame": 10},
            {"id": "c2", "segmentId": "body", "startFrame": 15, "endFrame": 30},
        ]
        MODULE.normalize_frame_ranges(scenes, captions, total_frames=31)
        self.assertEqual(scenes[0]["startFrame"], 0)
        self.assertEqual(scenes[-1]["endFrame"], 31)
        self.assertEqual(scenes[1]["endFrame"] - scenes[1]["startFrame"], 5)
        self.assertEqual(
            [item["endFrame"] for item in scenes[:-1]],
            [item["startFrame"] for item in scenes[1:]],
        )
        self.assertEqual(captions[-1]["endFrame"], 31)


if __name__ == "__main__":
    unittest.main()
