#!/usr/bin/env python3
"""Generate build_report.json with the exact keys qa_video.py requires."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()

    project = args.project.resolve()
    timing = project / "timing"

    paths = {
        "alignment": timing / "alignment-report.json",
        "captions": timing / "caption-timeline.json",
        "scenes": timing / "scene-timeline.json",
        "subtitles": timing / "subtitles.ass",
        "narration": timing / "narration.timestamped.final.wav",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("Missing timing artifacts: " + ", ".join(missing))

    alignment = json.loads(paths["alignment"].read_text(encoding="utf-8"))
    captions = json.loads(paths["captions"].read_text(encoding="utf-8"))
    scenes = json.loads(paths["scenes"].read_text(encoding="utf-8"))

    report: dict[str, Any] = {
        "version": 1,
        "totalFrames": scenes.get("totalFrames"),
        "durationMs": scenes.get("durationMs"),
        "durationSeconds": round(float(scenes.get("durationMs") or 0) / 1000, 3),
        "fps": scenes.get("fps"),
        "speechRate": alignment.get("speechRate"),
        "captionCount": len(captions.get("cards") or []),
        "scenes": scenes.get("scenes") or [],
        "alignmentReport": "timing/alignment-report.json",
        "captionTimeline": "timing/caption-timeline.json",
        "sceneTimeline": "timing/scene-timeline.json",
        "narrationAudio": "timing/narration.timestamped.final.wav",
        "subtitleFile": "timing/subtitles.ass",
        "narrationAudioSha256": sha256(paths["narration"]),
        "alignmentReportSha256": sha256(paths["alignment"]),
        "captionTimelineSha256": sha256(paths["captions"]),
        "sceneTimelineSha256": sha256(paths["scenes"]),
        "subtitleSha256": sha256(paths["subtitles"]),
    }

    build_path = project / "build_report.json"
    build_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {build_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
