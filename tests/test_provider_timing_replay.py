#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import qa_video


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare_timing_project(project: Path) -> dict:
    case = {
        "version": 3,
        "status": "approved",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "voice": {
            "resourceId": "seed-tts-2.0",
            "speaker": "test-speaker",
            "speechRate": 20,
            "sampleRate": 24000,
            "enableSubtitle": True,
            "requireSingleProviderRequest": True,
        },
        "segments": [
            {
                "id": f"scene-{index}",
                "narration": text,
                "captions": [
                    {
                        "id": f"caption-{index:03d}",
                        "zhText": text,
                        "enText": english,
                    }
                ],
            }
            for index, (text, english) in enumerate(
                (("甲。", "A."), ("乙。", "B."), ("丙。", "C.")), start=1
            )
        ],
        "timelineHolds": [],
    }
    manifest = {
        "version": 1,
        "captions": {
            "font": "PingFang SC",
            "fontSize": 72,
            "englishFontSize": 40,
            "positionY": 1500,
        },
    }
    write_json(project / "case.json", case)
    write_json(project / "render-manifest.json", manifest)
    raw = project / "audio/narration.raw.wav"
    raw.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(raw), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        target.writeframes(b"\x00\x00" * 36000)
    words = [
        {
            "key": f"word-{index:04d}",
            "word": text,
            "startMs": float((index - 1) * 500),
            "endMs": float(index * 500 - 100),
            "confidence": None,
            "requestIndex": 1,
        }
        for index, text in enumerate(("甲。", "乙。", "丙。"), start=1)
    ]
    report_path = project / "audio/narration.raw.wav.json"
    report = {
        "version": 1,
        "provider": "doubao-direct-v3",
        "status": "verified-provider-word-timestamps",
        "audioSha256": sha256(raw),
        "audioDurationMs": 1500.0,
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
        "xTtLogids": ["test-logid"],
        "providerRequests": [
            {
                "requestId": "test-request",
                "xTtLogid": "test-logid",
                "httpStatus": 200,
                "attemptCount": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "requestId": "test-request",
                        "xTtLogid": "test-logid",
                        "status": "succeeded",
                        "httpStatus": 200,
                    }
                ],
                "wordCount": 3,
            }
        ],
        "timestamps": {
            "source": "Doubao V3 sentence.words",
            "count": 3,
            "words": words,
        },
    }
    write_json(report_path, report)
    timing = project / "timing"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "build_timestamp_timeline.py"),
            "--audio",
            str(raw),
            "--tts-report",
            str(report_path),
            "--storyboard",
            str(project / "case.json"),
            "--case",
            str(project / "case.json"),
            "--output-dir",
            str(timing),
            "--fps",
            "30",
            "--caption-font",
            "PingFang SC",
            "--caption-font-size",
            "72",
            "--english-font-size",
            "40",
            "--caption-position-y",
            "1500",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    alignment = json.loads(
        (timing / "alignment-report.json").read_text(encoding="utf-8")
    )
    scenes = json.loads(
        (timing / "scene-timeline.json").read_text(encoding="utf-8")
    )
    build = {
        "alignmentReport": "timing/alignment-report.json",
        "captionTimeline": "timing/caption-timeline.json",
        "sceneTimeline": "timing/scene-timeline.json",
        "narrationAudio": "timing/narration.timestamped.final.wav",
        "subtitleFile": "timing/subtitles.ass",
        "rawNarrationAudio": "audio/narration.raw.wav",
        "ttsReport": "audio/narration.raw.wav.json",
        "wordTimeline": "timing/word-timeline.json",
        "totalFrames": scenes["totalFrames"],
        "captionCount": alignment["captionCount"],
        "resourceId": alignment["resourceId"],
        "speaker": alignment["speaker"],
        "speechRate": alignment["speechRate"],
        "enableSubtitle": alignment["enableSubtitle"],
        "requestMode": alignment["requestMode"],
        "providerRequestCount": alignment["providerRequestCount"],
        "providerAttemptCount": alignment["providerAttemptCount"],
        "providerLogids": alignment["providerLogids"],
        "narrationAudioSha256": sha256(
            timing / "narration.timestamped.final.wav"
        ),
        "rawNarrationAudioSha256": sha256(raw),
        "ttsReportSha256": sha256(report_path),
        "wordTimelineSha256": sha256(timing / "word-timeline.json"),
        "alignmentReportSha256": sha256(timing / "alignment-report.json"),
        "captionTimelineSha256": sha256(timing / "caption-timeline.json"),
        "sceneTimelineSha256": sha256(timing / "scene-timeline.json"),
        "subtitleSha256": sha256(timing / "subtitles.ass"),
        "caseSha256": sha256(project / "case.json"),
        "renderManifestSha256": sha256(project / "render-manifest.json"),
    }
    report_result, failures = qa_video.provider_timing_report(project, build)
    if failures or not report_result["ok"]:
        raise AssertionError(f"invalid provider replay fixture: {failures}")
    return build


def rebind_provider_source_hashes(project: Path, build: dict) -> None:
    raw = project / "audio/narration.raw.wav"
    report_path = project / "audio/narration.raw.wav.json"
    word_path = project / "timing/word-timeline.json"
    alignment_path = project / "timing/alignment-report.json"
    word = json.loads(word_path.read_text(encoding="utf-8"))
    word["rawNarrationAudioSha256"] = sha256(raw)
    word["ttsReportSha256"] = sha256(report_path)
    write_json(word_path, word)
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    alignment["rawNarrationAudioSha256"] = sha256(raw)
    alignment["sourceAudioSha256"] = sha256(raw)
    alignment["ttsReportSha256"] = sha256(report_path)
    alignment["sourceTtsReportSha256"] = sha256(report_path)
    alignment["wordTimelineSha256"] = sha256(word_path)
    write_json(alignment_path, alignment)
    build["rawNarrationAudioSha256"] = sha256(raw)
    build["ttsReportSha256"] = sha256(report_path)
    build["wordTimelineSha256"] = sha256(word_path)
    build["alignmentReportSha256"] = sha256(alignment_path)


class ProviderTimingReplayTests(unittest.TestCase):
    def test_rejects_replaced_raw_pcm_even_when_all_copied_hashes_are_rebound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            build = prepare_timing_project(project)
            raw_path = project / "audio/narration.raw.wav"
            raw_bytes = bytearray(raw_path.read_bytes())
            raw_bytes[100] = 1
            raw_path.write_bytes(raw_bytes)
            report_path = project / "audio/narration.raw.wav.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["audioSha256"] = sha256(raw_path)
            write_json(report_path, report)
            rebind_provider_source_hashes(project, build)

            result, failures = qa_video.provider_timing_report(project, build)
            self.assertFalse(result["ok"])
            self.assertTrue(
                any("narration PCM differs" in failure for failure in failures),
                failures,
            )

    def test_rejects_timeline_and_subtitle_tampering_after_hash_rebinding(self) -> None:
        mutations = {
            "scene": (
                "timing/scene-timeline.json",
                lambda document: document["scenes"][0].update(
                    {"endFrame": document["scenes"][0]["endFrame"] + 1}
                ),
                "sceneTimelineSha256",
                "scenes artifact differs",
            ),
            "caption": (
                "timing/caption-timeline.json",
                lambda document: document["cards"][0].update(
                    {"endFrame": document["cards"][0]["endFrame"] + 1}
                ),
                "captionTimelineSha256",
                "captions artifact differs",
            ),
            "ASS": (
                "timing/subtitles.ass",
                None,
                "subtitleSha256",
                "ASS subtitles differ",
            ),
        }
        for label, (relative, mutate, build_hash_field, expected_failure) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary).resolve()
                build = prepare_timing_project(project)
                path = project / relative
                if mutate is None:
                    path.write_text(
                        path.read_text(encoding="utf-8").replace("甲。", "乙。", 1),
                        encoding="utf-8",
                    )
                else:
                    document = json.loads(path.read_text(encoding="utf-8"))
                    mutate(document)
                    write_json(path, document)
                build[build_hash_field] = sha256(path)

                result, failures = qa_video.provider_timing_report(project, build)
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any(expected_failure in failure for failure in failures),
                    failures,
                )

    def test_rejects_a_globally_shifted_word_timeline_after_hash_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            build = prepare_timing_project(project)
            word_path = project / "timing/word-timeline.json"
            word = json.loads(word_path.read_text(encoding="utf-8"))
            for character in word["characters"]:
                character["timelineStartMs"] += 100.0
                character["timelineEndMs"] += 100.0
            write_json(word_path, word)
            alignment_path = project / "timing/alignment-report.json"
            alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
            alignment["wordTimelineSha256"] = sha256(word_path)
            write_json(alignment_path, alignment)
            build["wordTimelineSha256"] = sha256(word_path)
            build["alignmentReportSha256"] = sha256(alignment_path)

            result, failures = qa_video.provider_timing_report(project, build)
            self.assertFalse(result["ok"])
            self.assertTrue(
                any("words artifact differs" in failure for failure in failures),
                failures,
            )

    def test_rejects_missing_duplicate_and_out_of_order_provider_keys(self) -> None:
        mutations = {
            "missing": lambda words: words[1].pop("key"),
            "duplicate": lambda words: words[1].update({"key": words[0]["key"]}),
            "out-of-order": lambda words: (
                words[0].update({"key": "word-0002"}),
                words[1].update({"key": "word-0001"}),
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary).resolve()
                build = prepare_timing_project(project)
                report_path = project / "audio/narration.raw.wav.json"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                mutate(report["timestamps"]["words"])
                write_json(report_path, report)
                rebind_provider_source_hashes(project, build)

                result, failures = qa_video.provider_timing_report(project, build)
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any("provider source reconciliation failed" in item for item in failures),
                    failures,
                )


if __name__ == "__main__":
    unittest.main()
