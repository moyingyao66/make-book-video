#!/usr/bin/env python3
"""Verify a rendered book video and generate reproducible QA evidence."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any


def run(command: list[str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=capture,
        text=True,
        check=True,
    )


def packet_hash(path: Path) -> str:
    result = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-c",
            "copy",
            "-f",
            "md5",
            "-",
        ]
    )
    return result.stdout.strip()


def expected_duration(build: dict[str, Any]) -> float | None:
    for key in ("total_duration_s", "durationSeconds"):
        if build.get(key) is not None:
            return float(build[key])
    if build.get("durationMs") is not None:
        return float(build["durationMs"]) / 1000
    return None


def scene_starts(build: dict[str, Any], fps: float) -> list[float]:
    result: list[float] = []
    for scene in build.get("scenes") or []:
        if scene.get("start") is not None:
            result.append(float(scene["start"]))
        elif scene.get("startFrame") is not None:
            result.append(float(scene["startFrame"]) / fps)
        elif scene.get("timelineStartMs") is not None:
            result.append(float(scene["timelineStartMs"]) / 1000)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    video = project / "renders/video.mp4"
    audio_mix = project / "renders/audio_mix.m4a"
    build_path = project / "build_report.json"
    missing = [str(path) for path in (video, audio_mix, build_path) if not path.is_file()]
    if missing:
        raise SystemExit("Missing required QA files: " + ", ".join(missing))

    qa_dir = project / "renders/qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    probe = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(video),
            ]
        ).stdout
    )
    (qa_dir / "final-ffprobe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(video), "-f", "null", "-"])

    volume = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if volume.returncode != 0:
        raise RuntimeError(volume.stderr)
    (qa_dir / "final-volumedetect.txt").write_text(volume.stderr, encoding="utf-8")

    build = json.loads(build_path.read_text(encoding="utf-8"))
    human_path = qa_dir / "human-review.json"
    human = (
        json.loads(human_path.read_text(encoding="utf-8"))
        if human_path.is_file()
        else {"passed": False, "notes": "missing human-review.json"}
    )
    video_stream = next((item for item in probe["streams"] if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in probe["streams"] if item.get("codec_type") == "audio"), {})
    duration = float(probe["format"]["duration"])
    frame_rate = float(Fraction(video_stream.get("avg_frame_rate") or "0/1"))

    contact_interval = max(1, duration / 12)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            f"fps=1/{contact_interval:.3f},scale=270:480:force_original_aspect_ratio=decrease,"
            "pad=270:480:(ow-iw)/2:(oh-ih)/2:black,tile=4x3",
            "-frames:v",
            "1",
            str(qa_dir / "final-contact-sheet.png"),
        ],
        capture=False,
    )

    starts = [max(0, min(duration - 0.05, value + 0.12)) for value in scene_starts(build, frame_rate)]
    boundary_path: str | None = None
    if starts:
        frames = [round(value * frame_rate) for value in starts]
        rows = math.ceil(len(frames) / 4)
        select = "+".join(f"eq(n\\,{frame})" for frame in frames)
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video),
                "-vf",
                f"select={select},scale=270:480:force_original_aspect_ratio=decrease,"
                f"pad=270:480:(ow-iw)/2:(oh-ih)/2:black,tile=4x{rows}:"
                f"nb_frames={len(frames)}:padding=8:margin=8:color=black",
                "-frames:v",
                "1",
                str(qa_dir / "boundary-contact-sheet.png"),
            ],
            capture=False,
        )
        (qa_dir / "boundary-times.json").write_text(
            json.dumps(starts, indent=2) + "\n", encoding="utf-8"
        )
        boundary_path = "renders/qa/boundary-contact-sheet.png"

    expected = expected_duration(build)
    audio_matches = packet_hash(audio_mix) == packet_hash(video)
    failures: list[str] = []
    if video_stream.get("codec_name") != "h264":
        failures.append("video codec is not H.264")
    if (video_stream.get("width"), video_stream.get("height")) != (1080, 1920):
        failures.append("video is not 1080x1920")
    if abs(frame_rate - 30) > 0.01:
        failures.append("video is not 30 fps")
    if audio_stream.get("codec_name") != "aac":
        failures.append("audio codec is not AAC")
    if str(audio_stream.get("sample_rate")) != "48000":
        failures.append("audio is not 48 kHz")
    if expected is None or abs(duration - expected) > 0.12:
        failures.append("duration differs from build report")
    if not audio_matches:
        failures.append("final audio packets differ from approved mix")
    if human.get("passed") is not True:
        failures.append("human visual review is not recorded as passed")

    report = {
        "ok": not failures,
        "failures": failures,
        "video": {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": frame_rate,
            "durationSeconds": duration,
            "sizeBytes": int(probe["format"]["size"]),
        },
        "audio": {
            "codec": audio_stream.get("codec_name"),
            "sampleRate": audio_stream.get("sample_rate"),
            "packetHashMatches": audio_matches,
        },
        "decodePassed": True,
        "visualReview": human,
        "contactSheet": "renders/qa/final-contact-sheet.png",
        "boundaryContactSheet": boundary_path,
    }
    (qa_dir / "qa-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit("QA failed: " + "; ".join(failures))
    print(
        f"PASS {video_stream['width']}x{video_stream['height']} "
        f"{frame_rate:.3f}fps {duration:.3f}s | AAC {audio_stream['sample_rate']}Hz"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
