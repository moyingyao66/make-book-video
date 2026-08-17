from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/build_editor_plan.py"


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_wav(path: Path, duration_seconds: float, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(b"\x00\x00" * round(duration_seconds * sample_rate))


def prepare_project(project: Path) -> None:
    for relative, payload in (
        ("visuals/scene-one.png", b"scene-one"),
        ("assets/covers/one.png", b"cover-one"),
        ("assets/covers/two.png", b"cover-two"),
        ("assets/overlays/badge.png", b"badge"),
    ):
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    write_wav(project / "timing/narration.timestamped.final.wav", 1.0)
    write_wav(project / "assets/music/bed.wav", 1.0)
    write_wav(project / "assets/sfx/chime.wav", 0.2)

    segments = []
    cards = []
    scenes = []
    for index, text in enumerate(("甲。", "乙。", "丙。"), start=1):
        scene_id = f"scene-{index}"
        caption_id = f"caption-{index:03d}"
        start, end = (index - 1) * 10, index * 10
        segments.append(
            {
                "id": scene_id,
                "narration": text,
                "captions": [{"id": caption_id, "zhText": text, "enText": ""}],
            }
        )
        scenes.append(
            {
                "id": scene_id,
                "kind": "narrated",
                "startFrame": start,
                "endFrame": end,
            }
        )
        cards.append(
            {
                "id": caption_id,
                "segmentId": scene_id,
                "zhText": text,
                "enText": "",
                "startFrame": start,
                "endFrame": end,
            }
        )
    canvas = {"width": 1080, "height": 1920, "fps": 30}
    write_json(
        project / "case.json",
        {
            "version": 3,
            "status": "approved",
            "canvas": canvas,
            "segments": segments,
            "timelineHolds": [],
        },
    )
    write_json(
        project / "render-manifest.json",
        {
            "version": 3,
            "canvas": canvas,
            "sceneAssets": {
                "scene-1": {
                    "type": "image",
                    "path": "visuals/scene-one.png",
                    "fit": "cover",
                    "motion": "slow-zoom",
                    "overlays": [
                        {
                            "path": "assets/overlays/badge.png",
                            "layerRole": "book-badge",
                            "x": "100",
                            "y": "200",
                            "width": 240,
                            "height": 0,
                            "fadeInSeconds": 0.1,
                        }
                    ],
                },
                "scene-2": {
                    "type": "carousel",
                    "items": ["assets/covers/one.png", "assets/covers/two.png"],
                    "maxWidth": 620,
                    "maxHeight": 1040,
                    "framePadding": 30,
                    "backgroundColor": "#F3EADB",
                },
                "scene-3": {"type": "solid", "color": "#203040"},
            },
            "audio": {
                "narration": "timing/narration.timestamped.final.wav",
                "narrationVolume": 1.0,
                "bgm": {
                    "path": "assets/music/bed.wav",
                    "volume": 0.04,
                    "fadeInSeconds": 0.1,
                    "fadeOutSeconds": 0.2,
                },
                "sfx": [
                    {
                        "path": "assets/sfx/chime.wav",
                        "volume": 0.7,
                        "startSeconds": 0.5,
                        "fadeInSeconds": 0.03,
                        "fadeOutSeconds": 0.04,
                    }
                ],
            },
            "captions": {
                "mode": "zh-only",
                "requireEnglish": False,
                "font": "PingFang SC",
                "fontSize": 72,
                "englishFontSize": 40,
                "positionY": 1500,
                "safeBottomPx": 360,
                "burnIn": True,
            },
        },
    )
    write_json(
        project / "timing/scene-timeline.json",
        {
            "version": 1,
            "status": "verified-provider-timestamps",
            "fps": 30,
            "totalFrames": 30,
            "scenes": scenes,
        },
    )
    write_json(
        project / "timing/caption-timeline.json",
        {
            "version": 1,
            "status": "verified-provider-timestamps",
            "fps": 30,
            "cards": cards,
        },
    )
    narration = project / "timing/narration.timestamped.final.wav"
    write_json(
        project / "timing/alignment-report.json",
        {
            "version": 2,
            "status": "verified",
            "timestampSource": "Doubao V3 sentence.words",
            "providerRequestCount": 1,
            "providerAttemptCount": 1,
            "textCoverage": 1.0,
            "finalAudio": "timing/narration.timestamped.final.wav",
            "finalAudioSha256": digest(narration),
        },
    )


class EditorPlanTests(unittest.TestCase):
    def run_plan(self, project: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(project), *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_builds_stable_adapter_neutral_plan_with_split_carousel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)

            first = self.run_plan(project)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_bytes = (project / "editor-plan.json").read_bytes()
            second = self.run_plan(project)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first_bytes, (project / "editor-plan.json").read_bytes())

            plan = load_json(project / "editor-plan.json")
            self.assertEqual(plan["contract"], "make-book-video-editor-plan-v1")
            self.assertEqual(plan["status"], "planned-not-executed")
            self.assertTrue(plan["adapterNeutral"])
            self.assertFalse(plan["editorExecutionClaimed"])
            self.assertEqual(plan["canvas"], {"width": 1080, "height": 1920, "fps": 30})

            primary = plan["items"]["primaryScenes"]
            self.assertEqual(len(primary), 4)
            carousel = [item for item in primary if item["sceneId"] == "scene-2"]
            self.assertEqual(
                [(item["startFrame"], item["endFrame"]) for item in carousel],
                [(10, 15), (15, 20)],
            )
            self.assertEqual([item["manifestIndex"] for item in carousel], [0, 1])
            self.assertTrue(all(item["sourceSha256"] for item in carousel))
            solid = next(item for item in primary if item["sceneId"] == "scene-3")
            self.assertEqual((solid["sourcePath"], solid["sourceSha256"]), ("", ""))

            overlay = plan["items"]["overlays"][0]
            self.assertEqual(overlay["layerRole"], "book-badge")
            self.assertEqual((overlay["startFrame"], overlay["endFrame"]), (0, 10))
            audio = plan["items"]["audio"]
            self.assertEqual([item["role"] for item in audio], ["narration", "bgm", "sfx"])
            sfx = audio[-1]
            self.assertEqual((sfx["startFrame"], sfx["endFrame"]), (15, 21))
            self.assertEqual(sfx["startBasis"]["roundedDelayMs"], 500)
            self.assertEqual(plan["readback"]["status"], "required-not-captured")
            self.assertTrue(
                all(stage["status"] == "pending" for stage in plan["operations"]["stages"])
            )
            self.assertEqual(plan["operations"]["status"], "not-started")

    def test_rejects_unknown_scene_type_without_replacing_existing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            self.assertEqual(self.run_plan(project).returncode, 0)
            original = (project / "editor-plan.json").read_bytes()
            manifest = load_json(project / "render-manifest.json")
            manifest["sceneAssets"]["scene-1"]["type"] = "generated-montage"
            write_json(project / "render-manifest.json", manifest)

            failed = self.run_plan(project)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("unsupported type", failed.stderr)
            self.assertEqual(original, (project / "editor-plan.json").read_bytes())

    def test_rejects_flattened_mp4_as_primary_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            flattened = project / "renders/video.mp4"
            flattened.parent.mkdir(parents=True)
            flattened.write_bytes(b"flattened-final")
            manifest = load_json(project / "render-manifest.json")
            manifest["sceneAssets"]["scene-1"] = {
                "type": "video",
                "path": "renders/video.mp4",
                "fit": "cover",
                "loop": False,
            }
            write_json(project / "render-manifest.json", manifest)

            failed = self.run_plan(project)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("flattened media", failed.stderr)
            self.assertFalse((project / "editor-plan.json").exists())

            copied = project / "assets/pexels/copied.mp4"
            copied.parent.mkdir(parents=True)
            copied.write_bytes(flattened.read_bytes())
            manifest["sceneAssets"]["scene-1"]["path"] = "assets/pexels/copied.mp4"
            write_json(project / "render-manifest.json", manifest)
            duplicate = self.run_plan(project)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("duplicates renders/video.mp4", duplicate.stderr)

    def test_rejects_missing_or_out_of_project_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            manifest = load_json(project / "render-manifest.json")
            manifest["sceneAssets"]["scene-1"]["path"] = "visuals/missing.png"
            write_json(project / "render-manifest.json", manifest)
            missing = self.run_plan(project)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("does not exist", missing.stderr)

            manifest["sceneAssets"]["scene-1"]["path"] = "../outside.png"
            write_json(project / "render-manifest.json", manifest)
            escaped = self.run_plan(project)
            self.assertNotEqual(escaped.returncode, 0)
            self.assertIn("escapes the project", escaped.stderr)

    def test_rejects_scene_gap_and_out_of_range_sfx(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            timeline = load_json(project / "timing/scene-timeline.json")
            timeline["scenes"][1]["startFrame"] = 11
            write_json(project / "timing/scene-timeline.json", timeline)
            gap = self.run_plan(project)
            self.assertNotEqual(gap.returncode, 0)
            self.assertIn("gap or overlap", gap.stderr)

            prepare_project(project)
            manifest = load_json(project / "render-manifest.json")
            manifest["audio"]["sfx"][0].pop("startSeconds")
            manifest["audio"]["sfx"][0]["startFrame"] = 30
            write_json(project / "render-manifest.json", manifest)
            outside = self.run_plan(project)
            self.assertNotEqual(outside.returncode, 0)
            self.assertIn("starts outside", outside.stderr)

    def test_rejects_stale_alignment_audio_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            alignment = load_json(project / "timing/alignment-report.json")
            alignment["finalAudioSha256"] = "0" * 64
            write_json(project / "timing/alignment-report.json", alignment)

            failed = self.run_plan(project)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("finalAudioSha256", failed.stderr)

    def test_rejects_caption_drift_or_range_outside_owning_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            captions = load_json(project / "timing/caption-timeline.json")
            captions["cards"][0]["zhText"] = "变化"
            write_json(project / "timing/caption-timeline.json", captions)
            drift = self.run_plan(project)
            self.assertNotEqual(drift.returncode, 0)
            self.assertIn("differs from case.json", drift.stderr)

            prepare_project(project)
            captions = load_json(project / "timing/caption-timeline.json")
            captions["cards"][0]["endFrame"] = 11
            write_json(project / "timing/caption-timeline.json", captions)
            range_error = self.run_plan(project)
            self.assertNotEqual(range_error.returncode, 0)
            self.assertIn("outside scene", range_error.stderr)

    def test_output_cannot_overwrite_a_bound_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            original_case = (project / "case.json").read_bytes()

            failed = self.run_plan(project, "--output", "case.json")
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("overwrite a bound input/source", failed.stderr)
            self.assertEqual(original_case, (project / "case.json").read_bytes())

    def test_records_reference_renderer_effective_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "book"
            project.mkdir()
            prepare_project(project)
            manifest = load_json(project / "render-manifest.json")
            manifest["sceneAssets"]["scene-1"]["zoomStep"] = 0
            manifest["sceneAssets"]["scene-2"]["framePadding"] = 0
            manifest["audio"]["narrationVolume"] = 0
            manifest["audio"]["bgm"]["volume"] = 0
            manifest["audio"]["sfx"][0]["volume"] = 0
            write_json(project / "render-manifest.json", manifest)

            completed = self.run_plan(project)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = load_json(project / "editor-plan.json")
            scene_one = plan["items"]["primaryScenes"][0]
            carousel = plan["items"]["primaryScenes"][1]
            self.assertEqual(scene_one["effectiveParameters"]["zoomStep"], 0.0001)
            self.assertEqual(carousel["effectiveParameters"]["framePadding"], 36)
            audio = plan["items"]["audio"]
            self.assertEqual([item["volume"] for item in audio], [1.0, 0.035, 1.0])


if __name__ == "__main__":
    unittest.main()
