#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_ppm(path: Path, color: tuple[int, int, int]) -> None:
    width, height = 1080, 1920
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode() + bytes(color) * width * height)


def write_wav(path: Path, duration_seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 24000
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(b"\x00\x00" * round(sample_rate * duration_seconds))


def case_document() -> dict:
    segments = []
    for index, text in enumerate(("甲。", "乙。", "丙。"), start=1):
        segments.append(
            {
                "id": f"scene-{index}",
                "role": "body",
                "narration": text,
                "visualIntent": "test",
                "asset": "",
                "captions": [
                    {"id": f"caption-{index:03d}", "zhText": text, "enText": ""}
                ],
            }
        )
    return {
        "version": 1,
        "status": "approved",
        "book": {"title": "通用测试书", "authors": ["测试者"]},
        "audience": "test",
        "angle": "test",
        "claims": [],
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "voice": {
            "resourceId": "seed-tts-2.0",
            "speaker": "test-speaker",
            "speechRate": 20,
            "enableSubtitle": True,
            "requireSingleProviderRequest": True,
        },
        "timingEvidence": {},
        "segments": segments,
        "timelineHolds": [],
    }


def prepare_project(project: Path) -> None:
    case = case_document()
    write_json(project / "case.json", case)
    write_ppm(project / "visuals/intro.ppm", (30, 80, 130))
    write_ppm(project / "assets/covers/one.ppm", (180, 60, 40))
    write_ppm(project / "assets/covers/two.ppm", (40, 140, 80))
    write_json(
        project / "render-manifest.json",
        {
            "version": 1,
            "canvas": case["canvas"],
            "sceneAssets": {
                "scene-1": {
                    "type": "image",
                    "path": "visuals/intro.ppm",
                    "fit": "cover",
                    "intent": "test intro",
                    "assetStatus": "test-reviewed",
                },
                "scene-2": {
                    "type": "carousel",
                    "items": ["assets/covers/one.ppm", "assets/covers/two.ppm"],
                    "maxWidth": 620,
                    "maxHeight": 1040,
                    "backgroundColor": "0xf3eadb",
                    "intent": "test carousel",
                    "assetStatus": "test-reviewed",
                },
                "scene-3": {
                    "type": "solid",
                    "color": "0x203040",
                    "intent": "test close",
                    "assetStatus": "test-reviewed",
                },
            },
            "audio": {
                "narration": "timing/narration.timestamped.final.wav",
                "narrationVolume": 1.0,
                "bgm": {"path": "", "volume": 0.035},
                "sfx": [],
            },
            "captions": {
                "ass": "timing/subtitles.ass",
                "burnIn": True,
                "mode": "zh-only",
                "fontSize": 72,
                "englishFontSize": 40,
                "positionY": 1500,
                "safeBottomPx": 360,
            },
            "encoding": {
                "videoCodec": "libx264",
                "preset": "ultrafast",
                "crf": 30,
                "audioBitrate": "96k",
            },
        },
    )
    timing = project / "timing"
    narration = timing / "narration.timestamped.final.wav"
    write_wav(narration, 1.5)
    scenes = []
    cards = []
    for index in range(3):
        start, end = index * 15, (index + 1) * 15
        key = f"word-{index + 1:04d}"
        scenes.append(
            {
                "id": f"scene-{index + 1}",
                "kind": "narrated",
                "narration": ("甲。", "乙。", "丙。")[index],
                "startFrame": start,
                "endFrame": end,
                "providerWordKeys": [key],
                "alignmentStatus": "provider-timestamp",
            }
        )
        cards.append(
            {
                "id": f"caption-{index + 1:03d}",
                "segmentId": f"scene-{index + 1}",
                "zhText": ("甲。", "乙。", "丙。")[index],
                "startFrame": start,
                "endFrame": end,
                "sourceWordKeys": [key],
                "alignmentStatus": "provider-timestamp",
            }
        )
    write_json(
        timing / "scene-timeline.json",
        {
            "version": 1,
            "status": "verified-provider-timestamps",
            "fps": 30,
            "totalFrames": 45,
            "durationMs": 1500,
            "audio": str(narration),
            "scenes": scenes,
        },
    )
    write_json(
        timing / "caption-timeline.json",
        {
            "version": 1,
            "status": "verified-provider-timestamps",
            "fps": 30,
            "cards": cards,
        },
    )
    write_json(
        timing / "alignment-report.json",
        {
            "version": 1,
            "status": "verified",
            "timestampSource": "offline-test-fixture",
            "finalAudio": str(narration),
            "finalAudioSha256": sha256(narration),
            "requestMode": "single",
            "providerRequestCount": 1,
            "speechRate": 20,
            "providerLogids": ["test-logid"],
            "providerTimestampCount": 3,
            "alignedCharacterCount": 3,
            "segmentCount": 3,
            "captionCount": 3,
            "holds": [],
            "textCoverage": 1.0,
            "method": "test provider timestamps",
        },
    )
    (timing / "subtitles.ass").write_text(
        """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H40000000,-1,0,0,0,100,100,0,0,1,5,0,2,90,90,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.50,Caption,,0,0,0,,甲。
Dialogue: 0,0:00:00.50,0:00:01.00,Caption,,0,0,0,,乙。
Dialogue: 0,0:00:01.00,0:00:01.50,Caption,,0,0,0,,丙。
""",
        encoding="utf-8",
    )


def write_verified_editable_delivery(project: Path) -> None:
    scenes = json.loads(
        (project / "timing/scene-timeline.json").read_text(encoding="utf-8")
    )["scenes"]
    cards = json.loads(
        (project / "timing/caption-timeline.json").read_text(encoding="utf-8")
    )["cards"]
    scene_items = []
    for scene in scenes:
        scene_id = scene["id"]
        start = scene["startFrame"]
        end = scene["endFrame"]
        if scene_id == "scene-2":
            middle = start + (end - start) // 2
            scene_items.extend(
                [
                    {
                        "sceneId": scene_id,
                        "itemId": "editor-scene-2a",
                        "assetId": "asset-cover-1",
                        "trackId": "track-video",
                        "startFrame": start,
                        "endFrame": middle,
                        "sourcePath": "assets/covers/one.ppm",
                        "editable": True,
                    },
                    {
                        "sceneId": scene_id,
                        "itemId": "editor-scene-2b",
                        "assetId": "asset-cover-2",
                        "trackId": "track-video",
                        "startFrame": middle,
                        "endFrame": end,
                        "sourcePath": "assets/covers/two.ppm",
                        "editable": True,
                    },
                ]
            )
        else:
            source = "visuals/intro.ppm" if scene_id == "scene-1" else ""
            scene_items.append(
                {
                    "sceneId": scene_id,
                    "itemId": f"editor-{scene_id}",
                    "assetId": f"asset-{scene_id}",
                    "trackId": "track-video",
                    "startFrame": start,
                    "endFrame": end,
                    "sourcePath": source,
                    "editable": True,
                }
            )
    caption_items = [
        {
            "captionId": card["id"],
            "editorKey": f"editor-{card['id']}",
            "trackId": "track-captions",
            "startFrame": card["startFrame"],
            "endFrame": card["endFrame"],
            "editable": True,
        }
        for card in cards
    ]
    audio_items = [
        {
            "role": "narration",
            "itemId": "editor-narration",
            "assetId": "asset-narration",
            "trackId": "track-narration",
            "startFrame": 0,
            "endFrame": 45,
            "sourcePath": "timing/narration.timestamped.final.wav",
            "editable": True,
        }
    ]
    item_ids = [item["itemId"] for item in scene_items + audio_items]
    caption_keys = [item["editorKey"] for item in caption_items]
    document = {
        "version": 1,
        "status": "verified",
        "route": "openchatcut-local",
        "projectId": "project-test",
        "timelineId": "timeline-test",
        "editorUrl": "http://127.0.0.1/editor/project-test",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "sourceHashes": {
            "caseSha256": sha256(project / "case.json"),
            "renderManifestSha256": sha256(project / "render-manifest.json"),
            "alignmentReportSha256": sha256(project / "timing/alignment-report.json"),
            "sceneTimelineSha256": sha256(project / "timing/scene-timeline.json"),
            "captionTimelineSha256": sha256(project / "timing/caption-timeline.json"),
            "narrationAudioSha256": sha256(
                project / "timing/narration.timestamped.final.wav"
            ),
        },
        "assembly": {
            "flattenedPrimaryInput": False,
            "sceneItems": scene_items,
            "captionItems": caption_items,
            "audioItems": audio_items,
        },
        "readback": {
            "source": "openchatcut read_project + read_timeline + read_captions",
            "capturedAt": "2026-01-01T00:00:00Z",
            "projectReopened": True,
            "projectId": "project-test",
            "timelineId": "timeline-test",
            "assetIds": [item["assetId"] for item in scene_items + audio_items],
            "trackIds": ["track-video", "track-captions", "track-narration"],
            "itemIds": item_ids,
            "captionKeys": caption_keys,
        },
        "verificationFrames": [
            {"frame": 1, "evidence": "opening composed screenshot"},
            {"frame": 22, "evidence": "middle composed screenshot"},
            {"frame": 44, "evidence": "ending composed screenshot"},
        ],
        "optionalEditorExport": {"path": "", "sha256": ""},
        "notes": "offline test fixture",
    }
    write_json(project / "editable-delivery.json", document)


class InitializationTests(unittest.TestCase):
    def test_initializer_is_non_overwriting_and_uses_portable_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            command = [
                sys.executable,
                str(SCRIPTS / "init_case.py"),
                str(project),
                "--title",
                "测试书",
                "--author",
                "测试作者",
                "--opening-source",
                "pexels-video",
                "--body-source",
                "gpt-image",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            case_path = project / "case.json"
            first_hash = sha256(case_path)
            case = json.loads(case_path.read_text(encoding="utf-8"))
            self.assertEqual(case["book"]["title"], "测试书")
            self.assertEqual(case["voice"]["speechRate"], 20)
            self.assertEqual(
                case["voice"]["speaker"], "zh_male_cixingjieshuonan_uranus_bigtts"
            )
            self.assertEqual(
                case["narrativeProfile"]["id"], "cognition-awakening-v1"
            )
            self.assertEqual(case["segments"][0]["narration"], "今天分享的是。")
            self.assertEqual(
                case["segments"][1]["narration"], "测试作者的《测试书》。"
            )
            self.assertEqual(case["timelineHolds"][0]["durationFrames"], 45)
            self.assertEqual(case["version"], 3)
            self.assertEqual(
                case["visualSourcePolicy"],
                {
                    "selectionStatus": "confirmed",
                    "selectionMethod": "request_user_input",
                    "selectedAtProjectStart": True,
                    "openingSource": "pexels-video",
                    "bodySource": "gpt-image",
                    "recommendedDefaults": {
                        "openingSource": "pexels-video",
                        "bodySource": "gpt-image",
                    },
                    "silentFallbackAllowed": False,
                },
            )
            manifest = json.loads(
                (project / "render-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["version"], 3)
            self.assertEqual(manifest["sceneAssets"]["intro"]["type"], "video")
            self.assertEqual(
                manifest["sceneAssets"]["intro"]["sourceProvider"], "pexels"
            )
            for role in (
                "audience-problem",
                "alternative-explanation",
                "concrete-example",
                "practical-boundary",
                "audience-close",
            ):
                self.assertEqual(manifest["sceneAssets"][role]["type"], "image")
                self.assertEqual(
                    manifest["sceneAssets"][role]["sourceProvider"], "gpt-image"
                )
            self.assertTrue((project / "assets/pexels/intro-source.json").is_file())
            self.assertTrue((project / "editable-delivery.json").is_file())
            repeated = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(sha256(case_path), first_hash)

    def test_initializer_materializes_alternate_visual_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "init_case.py"),
                    str(project),
                    "--title",
                    "测试书",
                    "--opening-source",
                    "gpt-image",
                    "--body-source",
                    "pexels-video",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            case = json.loads((project / "case.json").read_text(encoding="utf-8"))
            manifest = json.loads(
                (project / "render-manifest.json").read_text(encoding="utf-8")
            )
            intro = manifest["sceneAssets"]["intro"]
            self.assertEqual(intro["type"], "image")
            self.assertEqual(intro["sourceProvider"], "gpt-image")
            self.assertEqual(intro["path"], "visuals/intro.png")
            self.assertEqual(intro["motion"], "slow-zoom")
            self.assertNotIn("sourceRecord", intro)
            for role in (
                "audience-problem",
                "alternative-explanation",
                "concrete-example",
                "practical-boundary",
                "audience-close",
            ):
                spec = manifest["sceneAssets"][role]
                expected_path = f"assets/pexels/{role}.mp4"
                self.assertEqual(spec["type"], "video")
                self.assertEqual(spec["sourceProvider"], "pexels")
                self.assertEqual(spec["path"], expected_path)
                case_segment = next(
                    item for item in case["segments"] if item["id"] == role
                )
                self.assertEqual(case_segment["asset"], expected_path)
                self.assertTrue(
                    (project / f"assets/pexels/{role}-source.json").is_file()
                )

    def test_initializer_refuses_to_guess_visual_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "init_case.py"),
                    str(project),
                    "--title",
                    "测试书",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--opening-source", result.stderr)
            self.assertIn("--body-source", result.stderr)
            self.assertFalse((project / "case.json").exists())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class GenericPipelineTests(unittest.TestCase):

    def test_render_and_qa_a_portable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_video.py"),
                    str(project),
                    "--render-only",
                ],
                check=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
            )
            build = json.loads((project / "build_report.json").read_text(encoding="utf-8"))
            self.assertEqual(build["totalFrames"], 45)
            self.assertEqual(build["captionCount"], 3)
            self.assertEqual(build["timestampSource"], "offline-test-fixture")
            self.assertTrue((project / "renders/video.mp4").is_file())

            preflight = json.loads(
                (project / "renders/qa/qa-preflight-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(preflight["structuralOk"])
            self.assertTrue(preflight["humanReviewPending"])

            review_path = project / "renders/qa/human-review.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["passed"] = True
            review["reviewedAt"] = "2026-01-01T00:00:00Z"
            review["reviewer"] = "test"
            review["checks"] = {key: True for key in review["checks"]}
            write_json(review_path, review)
            write_verified_editable_delivery(project)
            subprocess.run(
                [sys.executable, str(SCRIPTS / "qa_video.py"), str(project)],
                check=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
            )
            report = json.loads(
                (project / "renders/qa/qa-report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["ok"])
            self.assertTrue(report["audio"]["packetHashMatches"])
            release = json.loads(
                (project / "renders/qa/release-ready.json").read_text(encoding="utf-8")
            )
            self.assertTrue(release["ready"])
            self.assertEqual(release["videoSha256"], report["video"]["sha256"])
            self.assertEqual(release["editorProjectId"], "project-test")
            self.assertEqual(release["editorTimelineId"], "timeline-test")

    def test_editable_delivery_rejects_a_flattened_primary_video(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            path = project / "editable-delivery.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["assembly"]["flattenedPrimaryInput"] = True
            document["assembly"]["sceneItems"][0]["sourcePath"] = "renders/video.mp4"
            write_json(path, document)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_editable_delivery.py"),
                    str(project),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("flattened" in error for error in report["errors"]),
                report,
            )

    def test_editable_delivery_rejects_stale_source_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            case = json.loads((project / "case.json").read_text(encoding="utf-8"))
            case["angle"] = "changed after editor assembly"
            write_json(project / "case.json", case)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_editable_delivery.py"),
                    str(project),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("caseSha256" in error for error in report["errors"]),
                report,
            )

    def test_preflight_requires_resource_and_speaker(self) -> None:
        environment = {
            **os.environ,
            "DOUBAO_API_KEY": "test-only",
            "DOUBAO_TTS_RESOURCE_ID": "",
            "DOUBAO_TTS_SPEAKER": "",
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_environment.py")],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(report["readyForTimestampedNarration"])


if __name__ == "__main__":
    unittest.main()
