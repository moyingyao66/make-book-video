#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
import wave
import zlib
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import qa_video as qa_video_module
import render_video as render_video_module


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


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def write_png(
    path: Path,
    width: int = 1080,
    height: int = 1920,
    value: int = 96,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    row = b"\x00" + bytes([value]) * width
    compressed = zlib.compress(row * height, 9)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", compressed)
        + png_chunk(b"IEND", b"")
    )


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


def prepare_project(project: Path, *, delivery_ready: bool = False) -> None:
    case = case_document()
    if delivery_ready:
        case.update(
            {
                "version": 3,
                "status": "draft",
                "inputMode": "approved-script",
                "narrativeProfile": {"id": "custom"},
                "visualSourcePolicy": {
                    "selectionStatus": "confirmed",
                    "selectionMethod": "host-structured-choice",
                    "selectedAtProjectStart": True,
                    "openingSource": "gpt-image",
                    "bodySource": "gpt-image",
                    "silentFallbackAllowed": False,
                },
                "claims": [
                    {
                        "id": "claim-test",
                        "category": "interpretation",
                        "text": "Synthetic delivery fixture claim.",
                        "sourceUrl": "https://example.com/delivery-fixture",
                    }
                ],
                "copyReview": {
                    "status": "completed",
                    "reviewedBy": "delivery-fixture",
                    "checks": {
                        "singleMainThesis": True,
                        "audienceSituationConcrete": True,
                        "bookEvidenceMapped": True,
                        "examplesServeThesis": True,
                        "endingReturnsToAudience": True,
                        "readAloudNatural": True,
                    },
                },
                "approval": {
                    "contentApprovedByUser": False,
                    "storyboardApprovedByUser": False,
                    "paidGenerationAuthorized": False,
                    "receipt": {},
                },
            }
        )
        for segment in case["segments"]:
            segment["sourceClaimIds"] = ["claim-test"]
    write_json(project / "case.json", case)
    write_ppm(project / "visuals/intro.ppm", (30, 80, 130))
    write_ppm(project / "assets/covers/one.ppm", (180, 60, 40))
    write_ppm(project / "assets/covers/two.ppm", (40, 140, 80))
    write_ppm(project / "assets/overlays/book-badge.ppm", (210, 180, 40))
    write_wav(project / "assets/music/bed.wav", 1.5)
    write_wav(project / "assets/sfx/chime.wav", 0.2)
    write_wav(project / "assets/sfx/click.wav", 0.1)
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
                    "overlays": [
                        {
                            "path": "assets/overlays/book-badge.ppm",
                            "layerRole": "book-badge",
                            "x": "100",
                            "y": "200",
                            "width": 240,
                            "height": 0,
                            "fadeInSeconds": 0.1,
                        }
                    ],
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
                "bgm": {
                    "path": "assets/music/bed.wav",
                    "volume": 0.035,
                    "fadeInSeconds": 0.1,
                    "fadeOutSeconds": 0.2,
                },
                "sfx": [
                    {
                        "path": "assets/sfx/chime.wav",
                        "volume": 0.7,
                        "startFrame": 3,
                        "fadeInSeconds": 0.03,
                        "fadeOutSeconds": 0.04,
                    },
                    {
                        "path": "assets/sfx/click.wav",
                        "volume": 0.5,
                        "startSeconds": 1.0,
                        "fadeInSeconds": 0.0,
                        "fadeOutSeconds": 0.0,
                    },
                ],
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
    raw_narration = project / "audio/narration.raw.wav"
    write_wav(raw_narration, 1.5)
    tts_report_path = project / "audio/narration.raw.wav.json"
    provider_words = []
    for index, text in enumerate(("甲。", "乙。", "丙。"), start=1):
        provider_words.append(
            {
                "key": f"word-{index:04d}",
                "word": text,
                "startMs": float((index - 1) * 500),
                "endMs": float(index * 500),
                "confidence": None,
                "requestIndex": 1,
            }
        )
    write_json(
        tts_report_path,
        {
            "version": 1,
            "status": "verified-provider-word-timestamps",
            "output": "audio/narration.raw.wav",
            "audioSha256": sha256(raw_narration),
            "audioDurationMs": 1500.0,
            "sampleRate": 24000,
            "channels": 1,
            "sampleWidthBytes": 2,
            "provider": "doubao-direct-v3",
            "resourceId": "seed-tts-2.0",
            "speaker": "test-speaker",
            "speechRate": 20,
            "enableSubtitle": True,
            "requestMode": "single",
            "providerRequestCount": 1,
            "providerAttemptCount": 1,
            "timestamps": {
                "source": "Doubao V3 sentence.words",
                "level": "provider-word-or-character",
                "unit": "milliseconds",
                "count": 3,
                "words": provider_words,
            },
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
                            "status": "succeeded",
                            "httpStatus": 200,
                            "xTtLogid": "test-logid",
                        }
                    ],
                    "wordCount": 3,
                }
            ],
        },
    )
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
                "enText": "",
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
    word_characters = []
    for index, item in enumerate(provider_words, start=1):
        word_characters.append(
            {
                "key": f"word-{index:04d}-char-01",
                "providerWordKey": f"word-{index:04d}",
                "char": ("甲", "乙", "丙")[index - 1],
                "rawStartMs": item["startMs"],
                "rawEndMs": item["endMs"],
                "confidence": None,
                "segmentId": f"scene-{index}",
                "timelineStartMs": item["startMs"],
                "timelineEndMs": item["endMs"],
            }
        )
    write_json(
        timing / "word-timeline.json",
        {
            "version": 1,
            "status": "verified-provider-timestamps",
            "source": "Doubao V3 sentence.words",
            "rawNarrationAudio": "audio/narration.raw.wav",
            "rawNarrationAudioSha256": sha256(raw_narration),
            "ttsReport": "audio/narration.raw.wav.json",
            "ttsReportSha256": sha256(tts_report_path),
            "characters": word_characters,
        },
    )
    write_json(
        timing / "alignment-report.json",
        {
            "version": 2,
            "status": "verified",
            "timestampSource": "Doubao V3 sentence.words",
            "rawNarrationAudio": "audio/narration.raw.wav",
            "rawNarrationAudioSha256": sha256(raw_narration),
            "ttsReport": "audio/narration.raw.wav.json",
            "ttsReportSha256": sha256(tts_report_path),
            "wordTimeline": "timing/word-timeline.json",
            "wordTimelineSha256": sha256(timing / "word-timeline.json"),
            "sourceAudio": "audio/narration.raw.wav",
            "sourceAudioSha256": sha256(raw_narration),
            "sourceTtsReport": "audio/narration.raw.wav.json",
            "sourceTtsReportSha256": sha256(tts_report_path),
            "finalAudio": "timing/narration.timestamped.final.wav",
            "finalAudioSha256": sha256(narration),
            "resourceId": "seed-tts-2.0",
            "speaker": "test-speaker",
            "enableSubtitle": True,
            "requestMode": "single",
            "providerRequestCount": 1,
            "providerAttemptCount": 1,
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
    # Freeze test timing artifacts through the same deterministic provider
    # builder that final QA replays. Hand-authored timing fixtures would mask
    # frame-boundary and ASS drift instead of testing the production contract.
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "build_timestamp_timeline.py"),
            "--audio",
            str(raw_narration),
            "--tts-report",
            str(tts_report_path),
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
    if delivery_ready:
        preview = project / "audio/voice-preview.wav"
        write_wav(preview, 0.1)
        write_json(
            preview.with_suffix(preview.suffix + ".json"),
            {
                "audioSha256": sha256(preview),
                "resourceId": case["voice"]["resourceId"],
                "speaker": case["voice"]["speaker"],
                "speechRate": case["voice"]["speechRate"],
                "enableSubtitle": case["voice"]["enableSubtitle"],
            },
        )
        package = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_approval_package.py"), str(project)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if package.returncode != 0:
            raise AssertionError(package.stdout + package.stderr)
        approval = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "record_approval.py"),
                str(project),
                "--approved-by",
                "delivery-fixture",
                "--approved-at",
                "2026-01-01T00:00:00Z",
                "--voice-preview",
                "audio/voice-preview.wav",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if approval.returncode != 0:
            raise AssertionError(approval.stdout + approval.stderr)


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
                        "sourceSha256": sha256(project / "assets/covers/one.ppm"),
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
                        "sourceSha256": sha256(project / "assets/covers/two.ppm"),
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
                    "sourceSha256": sha256(project / source) if source else "",
                    "editable": True,
                }
            )
    overlay_items = [
        {
            "sceneId": "scene-1",
            "manifestIndex": 0,
            "itemId": "editor-overlay-scene-1-0",
            "assetId": "asset-overlay-book-badge",
            "trackId": "track-overlays",
            "startFrame": 0,
            "endFrame": scenes[0]["endFrame"],
            "sourcePath": "assets/overlays/book-badge.ppm",
            "sourceSha256": sha256(project / "assets/overlays/book-badge.ppm"),
            "layerRole": "book-badge",
            "x": "100",
            "y": "200",
            "width": 240,
            "height": 0,
            "fadeInSeconds": 0.1,
            "editable": True,
        }
    ]
    caption_items = [
        {
            "captionId": card["id"],
            "editorKey": f"editor-{card['id']}",
            "trackId": "track-captions",
            "startFrame": card["startFrame"],
            "endFrame": card["endFrame"],
            "zhText": card["zhText"],
            "enText": card.get("enText") or "",
            "editable": True,
        }
        for card in cards
    ]
    audio_items = [
        {
            "role": "narration",
            "manifestIndex": 0,
            "itemId": "editor-narration",
            "assetId": "asset-narration",
            "trackId": "track-narration",
            "startFrame": 0,
            "endFrame": 45,
            "sourcePath": "timing/narration.timestamped.final.wav",
            "sourceSha256": sha256(
                project / "timing/narration.timestamped.final.wav"
            ),
            "volume": 1.0,
            "fadeInSeconds": 0.0,
            "fadeOutSeconds": 0.0,
            "editable": True,
        },
        {
            "role": "bgm",
            "manifestIndex": 0,
            "itemId": "editor-bgm",
            "assetId": "asset-bgm",
            "trackId": "track-bgm",
            "startFrame": 0,
            "endFrame": 45,
            "sourcePath": "assets/music/bed.wav",
            "sourceSha256": sha256(project / "assets/music/bed.wav"),
            "volume": 0.035,
            "fadeInSeconds": 0.1,
            "fadeOutSeconds": 0.2,
            "editable": True,
        },
        {
            "role": "sfx",
            "manifestIndex": 0,
            "itemId": "editor-sfx-0",
            "assetId": "asset-sfx-0",
            "trackId": "track-sfx",
            "startFrame": 3,
            "endFrame": 9,
            "sourcePath": "assets/sfx/chime.wav",
            "sourceSha256": sha256(project / "assets/sfx/chime.wav"),
            "volume": 0.7,
            "fadeInSeconds": 0.03,
            "fadeOutSeconds": 0.04,
            "editable": True,
        },
        {
            "role": "sfx",
            "manifestIndex": 1,
            "itemId": "editor-sfx-1",
            "assetId": "asset-sfx-1",
            "trackId": "track-sfx",
            "startFrame": 30,
            "endFrame": 33,
            "sourcePath": "assets/sfx/click.wav",
            "sourceSha256": sha256(project / "assets/sfx/click.wav"),
            "volume": 0.5,
            "fadeInSeconds": 0.0,
            "fadeOutSeconds": 0.0,
            "editable": True,
        },
    ]
    item_ids = [
        item["itemId"] for item in scene_items + overlay_items + audio_items
    ]
    caption_keys = [item["editorKey"] for item in caption_items]
    verification_frames = []
    for position, frame_number in (("opening", 1), ("middle", 22), ("ending", 44)):
        evidence_path = project / f"renders/qa/editor-{position}.png"
        write_png(evidence_path, value=80 + frame_number)
        verification_frames.append(
            {
                "position": position,
                "frame": frame_number,
                "evidencePath": str(evidence_path.relative_to(project)),
                "sha256": sha256(evidence_path),
                "notes": f"{position} composed screenshot",
            }
        )
    document = {
        "version": 2,
        "status": "verified",
        "route": "chatcut",
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
            "overlayItems": overlay_items,
            "captionItems": caption_items,
            "audioItems": audio_items,
        },
        "readback": {},
        "verificationFrames": verification_frames,
        "optionalEditorExport": {"path": "", "sha256": ""},
        "notes": "offline test fixture",
    }
    readback_evidence = {
        "version": 2,
        "source": "ChatCut read_project + read_timeline + read_captions",
        "capturedAt": "2026-01-01T00:00:00Z",
        "projectReopened": True,
        "projectId": "project-test",
        "timelineId": "timeline-test",
        "canvas": document["canvas"],
        "assetIds": [
            item["assetId"] for item in scene_items + overlay_items + audio_items
        ],
        "trackIds": [
            "track-video",
            "track-overlays",
            "track-captions",
            "track-narration",
            "track-bgm",
            "track-sfx",
        ],
        "itemIds": item_ids,
        "captionKeys": caption_keys,
        "sceneItems": scene_items,
        "overlayItems": overlay_items,
        "captionItems": caption_items,
        "audioItems": audio_items,
    }
    readback_path = project / "editor/readback.json"
    write_json(readback_path, readback_evidence)
    document["readback"] = {
        "source": readback_evidence["source"],
        "capturedAt": readback_evidence["capturedAt"],
        "projectReopened": True,
        "projectId": "project-test",
        "timelineId": "timeline-test",
        "evidencePath": str(readback_path.relative_to(project)),
        "sha256": sha256(readback_path),
    }
    write_json(project / "editable-delivery.json", document)


class EditableDeliveryValidationTests(unittest.TestCase):
    def validate_project(self, project: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
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
        return result, json.loads(result.stdout)

    def test_verified_editable_delivery_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            prepare_project(project)
            write_verified_editable_delivery(project)
            result, report = self.validate_project(project)
            self.assertEqual(result.returncode, 0, report)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["verificationFrameCount"], 3)
            self.assertEqual(report["overlayCount"], 1)
            self.assertEqual(report["mappedOverlayCount"], 1)

    def test_fixed_case_symlink_outside_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            prepare_project(project)
            write_verified_editable_delivery(project)
            case_path = project / "case.json"
            outside = project.parent / "outside-case.json"
            outside.write_bytes(case_path.read_bytes())
            case_path.unlink()
            case_path.symlink_to(outside)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("case.json must not be a symlink" in error for error in report["errors"]),
                report,
            )

    def test_scene_items_must_cover_each_scene_without_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            path = project / "editable-delivery.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            scene_items = [
                item
                for item in document["assembly"]["sceneItems"]
                if item["sceneId"] == "scene-2"
            ]
            scene_items[0]["endFrame"] -= 1
            write_json(path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("not continuous" in error for error in report["errors"]),
                report,
            )

    def test_scene_source_path_must_match_render_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            path = project / "editable-delivery.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["assembly"]["sceneItems"][0]["sourcePath"] = (
                "assets/covers/one.ppm"
            )
            write_json(path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("does not match render manifest" in error for error in report["errors"]),
                report,
            )

    def test_scene_source_hash_binds_the_current_visual_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            source = project / "visuals/intro.ppm"
            source.write_bytes(source.read_bytes() + b"changed-after-editor-import")
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("scene item editor-scene-1 sourceSha256" in error for error in report["errors"]),
                report,
            )

    def test_overlay_mapping_is_one_to_one_and_exact(self) -> None:
        mutations = (
            ("missing", None, "missing manifest entries"),
            ("sourcePath", "assets/covers/one.ppm", "sourcePath differs"),
            ("sourceSha256", "0" * 64, "sourceSha256 is missing or stale"),
            ("endFrame", 14, "endFrame differs"),
            ("layerRole", "decoration", "layerRole differs"),
            ("x", "101", "x differs"),
            ("width", 241, "width differs"),
            ("fadeInSeconds", 0.2, "fadeInSeconds differs"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepare_project(project)
                write_verified_editable_delivery(project)
                path = project / "editable-delivery.json"
                document = json.loads(path.read_text(encoding="utf-8"))
                if field == "missing":
                    document["assembly"]["overlayItems"].clear()
                else:
                    document["assembly"]["overlayItems"][0][field] = value
                write_json(path, document)
                result, report = self.validate_project(project)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    any(expected_error in error for error in report["errors"]), report
                )

    def test_overlay_source_hash_binds_the_current_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            source = project / "assets/overlays/book-badge.ppm"
            source.write_bytes(source.read_bytes() + b"changed-after-editor-import")
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("overlay scene-1[0] sourceSha256" in error for error in report["errors"]),
                report,
            )

    def test_overlay_readback_must_match_the_reopened_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence_path = project / document["readback"]["evidencePath"]
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["overlayItems"][0]["x"] = "999"
            write_json(evidence_path, evidence)
            document["readback"]["sha256"] = sha256(evidence_path)
            write_json(delivery_path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("overlayItems differ" in error for error in report["errors"]),
                report,
            )

    def test_narration_source_must_match_render_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            path = project / "editable-delivery.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["assembly"]["audioItems"][0]["sourcePath"] = (
                "assets/covers/one.ppm"
            )
            write_json(path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("narration[0] sourcePath differs" in error for error in report["errors"]),
                report,
            )

    def test_caption_mapping_binds_exact_chinese_and_english_text(self) -> None:
        for field, value in (("zhText", "甲。 "), ("enText", "not empty")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepare_project(project)
                write_verified_editable_delivery(project)
                path = project / "editable-delivery.json"
                document = json.loads(path.read_text(encoding="utf-8"))
                document["assembly"]["captionItems"][0][field] = value
                write_json(path, document)
                result, report = self.validate_project(project)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    any(
                        f"caption caption-001 {field} differs" in error
                        for error in report["errors"]
                    ),
                    report,
                )

    def test_audio_mapping_is_exactly_bound_to_manifest(self) -> None:
        mutations = (
            ("sourcePath", "assets/sfx/click.wav", "sourcePath differs"),
            ("sourceSha256", "0" * 64, "sourceSha256 is missing or stale"),
            ("startFrame", 4, "startFrame differs"),
            ("endFrame", 10, "endFrame differs"),
            ("volume", 0.71, "volume differs"),
            ("fadeInSeconds", 0.1, "fadeInSeconds differs"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepare_project(project)
                write_verified_editable_delivery(project)
                path = project / "editable-delivery.json"
                document = json.loads(path.read_text(encoding="utf-8"))
                document["assembly"]["audioItems"][2][field] = value
                write_json(path, document)
                result, report = self.validate_project(project)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    any(expected_error in error for error in report["errors"]), report
                )

    def test_audio_mapping_rejects_unknown_or_non_bijective_roles(self) -> None:
        mutations = ("unknown-role", "missing-sfx", "duplicate-index")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepare_project(project)
                write_verified_editable_delivery(project)
                path = project / "editable-delivery.json"
                document = json.loads(path.read_text(encoding="utf-8"))
                audio_items = document["assembly"]["audioItems"]
                if mutation == "unknown-role":
                    audio_items[2]["role"] = "ambience"
                elif mutation == "missing-sfx":
                    audio_items.pop(3)
                else:
                    audio_items[3]["manifestIndex"] = 0
                write_json(path, document)
                result, report = self.validate_project(project)
                self.assertNotEqual(result.returncode, 0)
                if mutation == "unknown-role":
                    expected = "unknown role"
                elif mutation == "missing-sfx":
                    expected = "missing manifest entries"
                else:
                    expected = "duplicated for sfx[0]"
                self.assertTrue(any(expected in error for error in report["errors"]), report)

    def test_audio_mapping_rejects_fractional_or_string_numbers(self) -> None:
        mutations = (
            ("manifestIndex", 0.5, "manifestIndex"),
            ("startFrame", 3.5, "startFrame differs"),
            ("volume", "0.7", "volume differs"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary)
                prepare_project(project)
                write_verified_editable_delivery(project)
                path = project / "editable-delivery.json"
                document = json.loads(path.read_text(encoding="utf-8"))
                document["assembly"]["audioItems"][2][field] = value
                write_json(path, document)
                result, report = self.validate_project(project)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(
                    any(expected_error in error for error in report["errors"]), report
                )

    def test_readback_evidence_hash_and_normalized_content_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence_path = project / document["readback"]["evidencePath"]
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["captionItems"][0]["zhText"] = "读回文字被改动"
            write_json(evidence_path, evidence)
            document["readback"]["sha256"] = sha256(evidence_path)
            write_json(delivery_path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("captionItems differ" in error for error in report["errors"]), report
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence_path = project / document["readback"]["evidencePath"]
            evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("readback evidence SHA256" in error for error in report["errors"]),
                report,
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence_path = project / document["readback"]["evidencePath"]
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["audioItems"][2]["startFrame"] = 3.0
            write_json(evidence_path, evidence)
            document["readback"]["sha256"] = sha256(evidence_path)
            write_json(delivery_path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("startFrame must be a JSON integer" in error for error in report["errors"]),
                report,
            )

    def test_verification_frames_must_be_distinct_and_cover_three_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            path = project / "editable-delivery.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["verificationFrames"][1]["frame"] = 1
            write_json(path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("three distinct frames" in error for error in report["errors"]),
                report,
            )
            self.assertTrue(
                any("missing: middle" in error for error in report["errors"]),
                report,
            )

    def test_verification_evidence_hash_must_match_real_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            evidence = project / "renders/qa/editor-opening.png"
            evidence.write_bytes(evidence.read_bytes() + b"changed")
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("evidence SHA256" in error for error in report["errors"]),
                report,
            )

    def test_verification_evidence_must_be_decodable_canvas_sized_png(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence = project / document["verificationFrames"][0]["evidencePath"]
            evidence.write_bytes(b"not a png")
            document["verificationFrames"][0]["sha256"] = sha256(evidence)
            write_json(delivery_path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("invalid PNG signature" in error for error in report["errors"]),
                report,
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence = project / document["verificationFrames"][0]["evidencePath"]
            write_png(evidence, width=720, height=1280)
            document["verificationFrames"][0]["sha256"] = sha256(evidence)
            write_json(delivery_path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("dimensions 720x1280" in error for error in report["errors"]),
                report,
            )

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project)
            write_verified_editable_delivery(project)
            delivery_path = project / "editable-delivery.json"
            document = json.loads(delivery_path.read_text(encoding="utf-8"))
            evidence = project / document["verificationFrames"][0]["evidencePath"]
            ihdr = struct.pack(">IIBBBBB", 1080, 1920, 8, 0, 0, 0, 0)
            evidence.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + png_chunk(b"IHDR", ihdr)
                + png_chunk(b"IDAT", b"valid crc but not zlib")
                + png_chunk(b"IEND", b"")
            )
            document["verificationFrames"][0]["sha256"] = sha256(evidence)
            write_json(delivery_path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("not valid zlib data" in error for error in report["errors"]),
                report,
            )

    def test_verification_evidence_must_stay_inside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            prepare_project(project)
            write_verified_editable_delivery(project)
            outside = root / "outside-opening.png"
            outside.write_bytes(b"outside project evidence")
            path = project / "editable-delivery.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["verificationFrames"][0]["evidencePath"] = str(outside)
            document["verificationFrames"][0]["sha256"] = sha256(outside)
            write_json(path, document)
            result, report = self.validate_project(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(
                any("outside the project" in error for error in report["errors"]),
                report,
            )


class DeliveryMarkerLifecycleTests(unittest.TestCase):
    def stale_marker(self, project: Path) -> Path:
        marker = project / "renders/qa/delivery-ready.json"
        write_json(marker, {"ready": True, "videoSha256": "stale"})
        return marker

    def test_final_qa_removes_stale_marker_before_missing_input_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            marker = self.stale_marker(project)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "qa_video.py"), str(project)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_render_attempt_invalidates_stale_marker_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            marker = self.stale_marker(project)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "render_video.py"), str(project)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())


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
            self.assertEqual(case["version"], 4)
            self.assertEqual(case["visualStyleProfile"]["status"], "pending")
            self.assertEqual(
                case["visualStyleProfile"]["facePolicy"],
                "avoid-recognizable-faces",
            )
            self.assertEqual(
                case["narrativeProfile"]["shotStructure"]["minBodyShots"], 12
            )
            self.assertEqual(
                case["visualSourcePolicy"],
                {
                    "selectionStatus": "confirmed",
                    "selectionMethod": "host-structured-choice",
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
            self.assertEqual(manifest["version"], 4)
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


class RenderAudioContractTests(unittest.TestCase):
    def test_nonzero_sfx_fades_are_applied_before_delay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            audio = {
                "narration": "timing/narration.wav",
                "narrationVolume": 1.0,
                "sfx": [
                    {
                        "path": "assets/sfx/chime.wav",
                        "volume": 0.7,
                        "startFrame": 3,
                        "fadeInSeconds": 0.03,
                        "fadeOutSeconds": 0.04,
                    }
                ],
            }
            with mock.patch.object(render_video_module, "run") as run_mock:
                render_video_module.render_audio(
                    project,
                    audio,
                    project / "renders/audio.m4a",
                    duration=1.5,
                    fps=30,
                    bitrate="96k",
                )
            command = run_mock.call_args.args[0]
            filter_graph = command[command.index("-filter_complex") + 1]
            sfx_chain = next(
                item for item in filter_graph.split(";") if item.startswith("[1:a]")
            )
            self.assertIn("afade=t=in:st=0:d=0.030000", sfx_chain)
            self.assertIn(
                "areverse,afade=t=in:st=0:d=0.040000,areverse", sfx_chain
            )
            self.assertIn("adelay=100|100", sfx_chain)
            self.assertLess(sfx_chain.index("afade=t=in"), sfx_chain.index("adelay="))
            self.assertLess(sfx_chain.index("areverse"), sfx_chain.index("adelay="))

    def test_sfx_fades_must_be_non_negative_finite_numbers(self) -> None:
        invalid_values = (-0.1, float("nan"), float("inf"), "not-a-number")
        for field in ("fadeInSeconds", "fadeOutSeconds"):
            for value in invalid_values:
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as temporary:
                    project = Path(temporary).resolve()
                    sfx = {
                        "path": "assets/sfx/chime.wav",
                        "startFrame": 0,
                        "fadeInSeconds": 0.0,
                        "fadeOutSeconds": 0.0,
                    }
                    sfx[field] = value
                    with mock.patch.object(render_video_module, "run"), self.assertRaisesRegex(
                        ValueError, f"SFX 0 {field}"
                    ):
                        render_video_module.render_audio(
                            project,
                            {"narration": "timing/narration.wav", "sfx": [sfx]},
                            project / "renders/audio.m4a",
                            duration=1.0,
                            fps=30,
                            bitrate="96k",
                        )


class HumanEvidenceBindingTests(unittest.TestCase):
    def test_binds_in_order_and_rejects_duplicate_missing_and_escape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            first = project / "renders/qa/first.png"
            second = project / "renders/qa/second.png"
            write_png(first)
            write_png(second, value=120)
            bound, failures = qa_video_module.bind_human_evidence(
                project,
                {"evidence": ["renders/qa/second.png", "renders/qa/first.png"]},
                required_paths=["renders/qa/first.png", "renders/qa/second.png"],
            )
            self.assertEqual(failures, [])
            self.assertEqual(
                [item["path"] for item in bound],
                ["renders/qa/second.png", "renders/qa/first.png"],
            )

            _, failures = qa_video_module.bind_human_evidence(
                project,
                {
                    "evidence": [
                        "renders/qa/first.png",
                        "renders/qa/first.png",
                        "renders/qa/missing.png",
                        "../outside.png",
                    ]
                },
                required_paths=["renders/qa/second.png"],
            )
            self.assertTrue(any("duplicated" in value for value in failures), failures)
            self.assertTrue(any("missing" in value for value in failures), failures)
            self.assertTrue(any("escapes" in value for value in failures), failures)
            self.assertTrue(any("not reviewed and bound" in value for value in failures), failures)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class GenericPipelineTests(unittest.TestCase):

    def test_provider_qa_reopens_sources_after_all_copied_hashes_are_forged(self) -> None:
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
            build_path = project / "build_report.json"
            alignment_path = project / "timing/alignment-report.json"
            word_path = project / "timing/word-timeline.json"
            tts_path = project / "audio/narration.raw.wav.json"
            build = json.loads(build_path.read_text(encoding="utf-8"))
            alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
            word = json.loads(word_path.read_text(encoding="utf-8"))
            tts = json.loads(tts_path.read_text(encoding="utf-8"))

            # Forge both the source contents and every copied hash/semantic field.
            # QA must still compare the sources to case.voice and provider words.
            tts["speaker"] = "forged-speaker"
            word["characters"][0]["char"] = "乙"
            write_json(tts_path, tts)
            word["ttsReportSha256"] = sha256(tts_path)
            write_json(word_path, word)
            alignment["speaker"] = "forged-speaker"
            alignment["ttsReportSha256"] = sha256(tts_path)
            alignment["wordTimelineSha256"] = sha256(word_path)
            write_json(alignment_path, alignment)
            build["speaker"] = "forged-speaker"
            build["ttsReportSha256"] = sha256(tts_path)
            build["wordTimelineSha256"] = sha256(word_path)
            build["alignmentReportSha256"] = sha256(alignment_path)

            timing, failures = qa_video_module.provider_timing_report(project, build)
            self.assertFalse(timing["ok"])
            self.assertTrue(
                any("case.voice.speaker" in message for message in failures), failures
            )

            # Restore the voice semantics while leaving the forged word timeline
            # and rebind every copied hash again. Character reconciliation must fail.
            tts["speaker"] = "test-speaker"
            write_json(tts_path, tts)
            word["ttsReportSha256"] = sha256(tts_path)
            write_json(word_path, word)
            alignment["speaker"] = "test-speaker"
            alignment["ttsReportSha256"] = sha256(tts_path)
            alignment["wordTimelineSha256"] = sha256(word_path)
            write_json(alignment_path, alignment)
            build["speaker"] = "test-speaker"
            build["ttsReportSha256"] = sha256(tts_path)
            build["wordTimelineSha256"] = sha256(word_path)
            build["alignmentReportSha256"] = sha256(alignment_path)
            timing, failures = qa_video_module.provider_timing_report(project, build)
            self.assertFalse(timing["ok"])
            self.assertTrue(
                any("differs from provider words" in message for message in failures),
                failures,
            )

    def test_render_and_qa_a_portable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            prepare_project(project, delivery_ready=True)
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
            self.assertEqual(build["timestampSource"], "Doubao V3 sentence.words")
            for path_field, hash_field in (
                ("rawNarrationAudio", "rawNarrationAudioSha256"),
                ("ttsReport", "ttsReportSha256"),
                ("wordTimeline", "wordTimelineSha256"),
            ):
                self.assertEqual(
                    build[hash_field], sha256(project / build[path_field])
                )
            self.assertTrue((project / "renders/video.mp4").is_file())

            preflight = json.loads(
                (project / "renders/qa/qa-preflight-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(preflight["structuralOk"])
            self.assertTrue(preflight["humanReviewPending"])

            write_verified_editable_delivery(project)
            review_path = project / "renders/qa/human-review.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["passed"] = True
            review["reviewedAt"] = "2026-01-01T00:00:00Z"
            review["reviewer"] = "test"
            review["editableDeliverySha256"] = sha256(
                project / "editable-delivery.json"
            )
            review["checks"] = {key: True for key in review["checks"]}
            write_json(review_path, review)
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
            self.assertEqual(
                [item["path"] for item in report["humanEvidence"]],
                [
                    "renders/qa/final-contact-sheet.png",
                    "renders/qa/boundary-contact-sheet.png",
                ],
            )
            delivery = json.loads(
                (project / "renders/qa/delivery-ready.json").read_text(encoding="utf-8")
            )
            self.assertTrue(delivery["ready"])
            self.assertEqual(delivery["videoSha256"], report["video"]["sha256"])
            self.assertEqual(
                delivery["qaReportSha256"],
                sha256(project / "renders/qa/qa-report.json"),
            )
            self.assertEqual(
                delivery["buildReportSha256"], sha256(project / "build_report.json")
            )
            self.assertEqual(
                delivery["humanReviewSha256"], sha256(review_path)
            )
            self.assertEqual(
                delivery["editableDeliverySha256"],
                sha256(project / "editable-delivery.json"),
            )
            self.assertEqual(delivery["editorProjectId"], "project-test")
            self.assertEqual(delivery["editorTimelineId"], "timeline-test")
            self.assertEqual(delivery["humanEvidence"], report["humanEvidence"])
            for item in delivery["humanEvidence"]:
                self.assertEqual(item["sha256"], sha256(project / item["path"]))
            for path_field, hash_field in (
                ("rawNarrationAudio", "rawNarrationAudioSha256"),
                ("ttsReport", "ttsReportSha256"),
                ("wordTimeline", "wordTimelineSha256"),
            ):
                self.assertEqual(delivery[path_field], build[path_field])
                self.assertEqual(delivery[hash_field], build[hash_field])
            self.assertEqual(
                list((project / "renders/qa").glob(".delivery-ready.json.*.tmp")),
                [],
            )

            evidence = project / "renders/qa/editor-middle.png"
            evidence.write_bytes(evidence.read_bytes() + b"stale")
            failed = subprocess.run(
                [sys.executable, str(SCRIPTS / "qa_video.py"), str(project)],
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(
                (project / "renders/qa/delivery-ready.json").exists(),
                "a failed final QA must not leave the previous delivery marker",
            )

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
            "PATH": "/bin",
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
