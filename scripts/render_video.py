#!/usr/bin/env python3
"""Render any validated make-book-video project from its timeline and manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from validate_case import validate_case, validate_manifest


SKILL_DIR = Path(__file__).resolve().parents[1]


def run(command: list[str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=capture)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_path(project: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    if path.is_absolute():
        raise ValueError(f"Render paths must be project-relative: {path}")
    resolved = (project / path).resolve()
    resolved.relative_to(project)
    return resolved


def fit_filter(width: int, height: int, fit: str) -> str:
    if fit == "contain":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    if fit == "stretch":
        return f"scale={width}:{height}"
    if fit != "cover":
        raise ValueError(f"Unsupported fit mode: {fit}")
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def encode_args(encoding: dict[str, Any], fps: int) -> list[str]:
    return [
        "-c:v",
        str(encoding.get("videoCodec") or "libx264"),
        "-preset",
        str(encoding.get("preset") or "fast"),
        "-crf",
        str(int(encoding.get("crf") or 18)),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-an",
    ]


def render_image(
    source: Path,
    output: Path,
    frames: int,
    canvas: dict[str, int],
    encoding: dict[str, Any],
    spec: dict[str, Any],
    project: Path,
) -> None:
    width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
    overlays = spec.get("overlays") or []
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", str(source)]
    for overlay in overlays:
        command.extend(["-loop", "1", "-i", str(project_path(project, overlay.get("path")))])

    base = fit_filter(width, height, str(spec.get("fit") or "cover"))
    if spec.get("motion") == "slow-zoom":
        step = float(spec.get("zoomStep") or 0.0001)
        limit = float(spec.get("zoomLimit") or 1.04)
        base += (
            f",zoompan=z='min(pzoom+{step:.7f},{limit:.4f})':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps}"
        )
    else:
        base += f",fps={fps}"
    base += ",setsar=1"

    if overlays:
        filters = [f"[0:v]{base}[base0]"]
        current = "base0"
        for index, overlay in enumerate(overlays, start=1):
            overlay_width = int(overlay.get("width") or 0)
            overlay_height = int(overlay.get("height") or 0)
            if overlay_width > 0 and overlay_height > 0:
                scale = f"scale={overlay_width}:{overlay_height}"
            elif overlay_width > 0:
                scale = f"scale={overlay_width}:-1"
            elif overlay_height > 0:
                scale = f"scale=-1:{overlay_height}"
            else:
                scale = "scale=iw:ih"
            fade_seconds = float(overlay.get("fadeInSeconds") or 0)
            chain = f"[{index}:v]{scale},format=rgba"
            if fade_seconds > 0:
                chain += f",fade=t=in:st=0:d={fade_seconds:.3f}:alpha=1"
            overlay_label = f"overlay{index}"
            filters.append(f"{chain}[{overlay_label}]")
            output_label = f"composite{index}"
            x = str(overlay.get("x", "(W-w)/2"))
            y = str(overlay.get("y", "(H-h)/2"))
            filters.append(
                f"[{current}][{overlay_label}]overlay=x={x}:y={y}:"
                f"shortest=1:eof_action=pass[{output_label}]"
            )
            current = output_label
        filters.append(f"[{current}]format=yuv420p[v]")
        command.extend(["-filter_complex", ";".join(filters), "-map", "[v]"])
    else:
        command.extend(["-vf", base + ",format=yuv420p"])
    command.extend(["-frames:v", str(frames), *encode_args(encoding, fps), str(output)])
    run(command)


def render_video_scene(
    source: Path,
    output: Path,
    frames: int,
    canvas: dict[str, int],
    encoding: dict[str, Any],
    spec: dict[str, Any],
) -> None:
    width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if spec.get("loop", True):
        command.extend(["-stream_loop", "-1"])
    if float(spec.get("startSeconds") or 0) > 0:
        command.extend(["-ss", str(float(spec["startSeconds"]))])
    command.extend(["-i", str(source)])
    command.extend(
        [
            "-vf",
            fit_filter(width, height, str(spec.get("fit") or "cover"))
            + f",fps={fps},setsar=1,format=yuv420p",
            "-frames:v",
            str(frames),
            *encode_args(encoding, fps),
            str(output),
        ]
    )
    run(command)


def render_solid(
    output: Path,
    frames: int,
    canvas: dict[str, int],
    encoding: dict[str, Any],
    spec: dict[str, Any],
) -> None:
    width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
    color = str(spec.get("color") or "black")
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={width}x{height}:r={fps}",
            "-frames:v",
            str(frames),
            *encode_args(encoding, fps),
            str(output),
        ]
    )


def carousel_frame_counts(total: int, count: int, spec: dict[str, Any]) -> list[int]:
    explicit = spec.get("framesPerItem")
    if explicit is not None:
        values = [int(value) for value in explicit]
        if len(values) != count or any(value <= 0 for value in values) or sum(values) != total:
            raise ValueError("carousel framesPerItem must be positive and sum to scene frames")
        return values
    if spec.get("itemFrames") is not None:
        value = int(spec["itemFrames"])
        if value <= 0 or value * count != total:
            raise ValueError("carousel itemFrames multiplied by item count must equal scene frames")
        return [value] * count
    base, remainder = divmod(total, count)
    if base <= 0:
        raise ValueError("carousel scene has fewer frames than items")
    return [base + (1 if index < remainder else 0) for index in range(count)]


def render_carousel_item(
    source: Path,
    output: Path,
    frames: int,
    canvas: dict[str, int],
    encoding: dict[str, Any],
    spec: dict[str, Any],
) -> None:
    width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
    max_width = int(spec.get("maxWidth") or round(width * 0.58))
    max_height = int(spec.get("maxHeight") or round(height * 0.55))
    padding = int(spec.get("framePadding") or 36)
    frame_width = max_width + padding * 2
    frame_height = max_height + padding * 2
    background = str(spec.get("backgroundColor") or "0xf3eadb")
    filter_chain = (
        f"scale={max_width}:{max_height}:force_original_aspect_ratio=decrease,"
        f"pad={frame_width}:{frame_height}:(ow-iw)/2:(oh-ih)/2:color=white,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={background},"
        f"fps={fps},setsar=1,format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(source),
            "-vf",
            filter_chain,
            "-frames:v",
            str(frames),
            *encode_args(encoding, fps),
            str(output),
        ]
    )


def concat_videos(paths: list[Path], output: Path, list_path: Path) -> None:
    lines = []
    for path in paths:
        escaped = str(path).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-an",
            str(output),
        ]
    )


def count_video_frames(path: Path) -> int:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ]
    )
    return int(result.stdout.strip())


def render_audio(
    project: Path,
    audio: dict[str, Any],
    output: Path,
    duration: float,
    fps: int,
    bitrate: str,
) -> None:
    narration = project_path(project, audio.get("narration"))
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(narration)]
    filters = [
        f"[0:a]aresample=48000,volume={float(audio.get('narrationVolume') or 1.0):.6f},"
        f"apad=whole_dur={duration:.6f},atrim=duration={duration:.6f}[narr]"
    ]
    labels = ["[narr]"]
    input_index = 1
    bgm = audio.get("bgm") or {}
    if str(bgm.get("path") or "").strip():
        command.extend(["-stream_loop", "-1", "-i", str(project_path(project, bgm.get("path")))])
        fade_in = max(0.0, float(bgm.get("fadeInSeconds") or 0))
        fade_out = max(0.0, float(bgm.get("fadeOutSeconds") or 0))
        chain = (
            f"[{input_index}:a]aresample=48000,atrim=duration={duration:.6f},"
            f"asetpts=PTS-STARTPTS,volume={float(bgm.get('volume') or 0.035):.6f}"
        )
        if fade_in > 0:
            chain += f",afade=t=in:st=0:d={min(fade_in, duration):.3f}"
        if fade_out > 0 and duration > 0:
            start = max(0.0, duration - fade_out)
            chain += f",afade=t=out:st={start:.3f}:d={min(fade_out, duration):.3f}"
        filters.append(chain + "[bgm]")
        labels.append("[bgm]")
        input_index += 1
    for sfx_index, sfx in enumerate(audio.get("sfx") or [], start=1):
        command.extend(["-i", str(project_path(project, sfx.get("path")))])
        if sfx.get("startFrame") is not None:
            delay_ms = round(int(sfx["startFrame"]) * 1000 / fps)
        else:
            delay_ms = round(float(sfx.get("startSeconds") or 0) * 1000)
        label = f"sfx{sfx_index}"
        filters.append(
            f"[{input_index}:a]aresample=48000,volume={float(sfx.get('volume') or 1.0):.6f},"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        labels.append(f"[{label}]")
        input_index += 1
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
        f"alimiter=limit=0.95,apad=whole_dur={duration:.6f},"
        f"atrim=duration={duration:.6f}[mix]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[mix]",
            "-c:a",
            "aac",
            "-b:a",
            bitrate,
            "-ar",
            "48000",
            "-t",
            f"{duration:.6f}",
            str(output),
        ]
    )
    run(command)


def ffmpeg_filter_path(path: Path) -> str:
    value = str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    for character in (",", "[", "]", ";"):
        value = value.replace(character, "\\" + character)
    return f"'{value}'"


def mux_video(
    base_video: Path,
    audio_mix: Path,
    subtitle: Path,
    output: Path,
    total_frames: int,
    duration: float,
    fps: int,
    encoding: dict[str, Any],
    burn_captions: bool,
) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(base_video),
        "-i",
        str(audio_mix),
    ]
    if burn_captions:
        command.extend(["-vf", f"ass={ffmpeg_filter_path(subtitle)},format=yuv420p"])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-frames:v",
            str(total_frames),
            "-c:v",
            str(encoding.get("videoCodec") or "libx264"),
            "-preset",
            str(encoding.get("preset") or "fast"),
            "-crf",
            str(int(encoding.get("crf") or 18)),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "-t",
            f"{duration:.6f}",
            str(output),
        ]
    )
    run(command)


def refresh_human_review(project: Path, video_hash: str) -> None:
    path = project / "renders/qa/human-review.json"
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("videoSha256") == video_hash:
            return
    template = json.loads(
        (SKILL_DIR / "assets/human-review-template.json").read_text(encoding="utf-8")
    )
    template["videoSha256"] = video_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    for executable in ("ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            raise SystemExit(f"Missing required executable: {executable}")

    case_path = project / "case.json"
    manifest_path = project / "render-manifest.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_case(case, require_approved=True)
    errors.extend(validate_manifest(project, case, manifest, check_assets=True))
    if errors:
        raise SystemExit("Render validation failed: " + "; ".join(errors))

    timing_dir = project / "timing"
    scene_path = timing_dir / "scene-timeline.json"
    alignment_path = timing_dir / "alignment-report.json"
    caption_path = timing_dir / "caption-timeline.json"
    subtitle_path = project_path(project, (manifest.get("captions") or {}).get("ass"))
    for path in (scene_path, alignment_path, caption_path, subtitle_path):
        if not path.is_file():
            raise SystemExit(f"Missing frozen timing input: {path}")
    scene_document = json.loads(scene_path.read_text(encoding="utf-8"))
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    captions = json.loads(caption_path.read_text(encoding="utf-8"))
    canvas = {key: int(value) for key, value in (manifest.get("canvas") or {}).items()}
    fps = canvas["fps"]
    total_frames = int(scene_document.get("totalFrames") or 0)
    duration = total_frames / fps
    if total_frames <= 0:
        raise SystemExit("Scene timeline has no renderable frames")
    scenes = scene_document.get("scenes") or []
    if not scenes:
        raise SystemExit("Scene timeline has no scenes")

    renders_dir = project / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    encoding = manifest.get("encoding") or {}
    scene_specs = manifest.get("sceneAssets") or {}
    with tempfile.TemporaryDirectory(prefix=".render-", dir=str(renders_dir)) as temporary:
        work = Path(temporary)
        rendered_scenes: list[Path] = []
        for index, scene in enumerate(scenes, start=1):
            scene_id = str(scene.get("id") or "")
            spec = scene_specs[scene_id]
            frames = int(scene.get("endFrame") or 0) - int(scene.get("startFrame") or 0)
            if frames <= 0:
                raise SystemExit(f"Scene {scene_id} has no positive frame duration")
            output = work / f"scene-{index:03d}.mp4"
            scene_type = spec["type"]
            if scene_type == "image":
                render_image(project_path(project, spec.get("path")), output, frames, canvas, encoding, spec, project)
            elif scene_type == "video":
                render_video_scene(project_path(project, spec.get("path")), output, frames, canvas, encoding, spec)
            elif scene_type == "solid":
                render_solid(output, frames, canvas, encoding, spec)
            elif scene_type == "carousel":
                items = [project_path(project, value) for value in spec.get("items") or []]
                counts = carousel_frame_counts(frames, len(items), spec)
                carousel_parts: list[Path] = []
                for item_index, (item, item_frames) in enumerate(zip(items, counts), start=1):
                    part = work / f"scene-{index:03d}-item-{item_index:02d}.mp4"
                    render_carousel_item(item, part, item_frames, canvas, encoding, spec)
                    carousel_parts.append(part)
                concat_videos(carousel_parts, output, work / f"carousel-{index:03d}.txt")
            else:
                raise SystemExit(f"Unsupported scene type: {scene_type}")
            actual_frames = count_video_frames(output)
            if actual_frames != frames:
                raise SystemExit(
                    f"Scene {scene_id} rendered {actual_frames} frames, expected {frames}"
                )
            rendered_scenes.append(output)

        base_video = work / "video-base.mp4"
        concat_videos(rendered_scenes, base_video, work / "scenes.txt")
        base_frames = count_video_frames(base_video)
        if base_frames != total_frames:
            raise SystemExit(
                f"Concatenated video has {base_frames} frames, expected {total_frames}"
            )
        audio_mix = renders_dir / "audio_mix.m4a"
        render_audio(
            project,
            manifest.get("audio") or {},
            audio_mix,
            duration,
            fps,
            str(encoding.get("audioBitrate") or "192k"),
        )
        output_video = renders_dir / "video.mp4"
        mux_video(
            base_video,
            audio_mix,
            subtitle_path,
            output_video,
            total_frames,
            duration,
            fps,
            encoding,
            bool((manifest.get("captions") or {}).get("burnIn", True)),
        )

    actual_frames = count_video_frames(output_video)
    if actual_frames != total_frames:
        raise SystemExit(f"Final video has {actual_frames} frames, expected {total_frames}")
    video_hash = sha256(output_video)
    narration_path = project_path(project, (manifest.get("audio") or {}).get("narration"))
    build_report = {
        "version": 3,
        "status": "rendered-pending-human-review",
        "fps": fps,
        "totalFrames": total_frames,
        "durationSeconds": duration,
        "timestampSource": alignment.get("timestampSource") or "unspecified",
        "requestMode": alignment.get("requestMode"),
        "providerRequestCount": alignment.get("providerRequestCount"),
        "providerTimestampCount": alignment.get("providerTimestampCount"),
        "speechRate": alignment.get("speechRate"),
        "textCoverage": alignment.get("textCoverage"),
        "holds": alignment.get("holds") or [],
        "captionCount": len(captions.get("cards") or []),
        "providerAlignedCaptionCount": len(
            [
                card
                for card in captions.get("cards") or []
                if card.get("alignmentStatus") == "provider-timestamp"
                and card.get("sourceWordKeys")
            ]
        ),
        "narrationAudio": str(narration_path.relative_to(project)),
        "narrationAudioSha256": sha256(narration_path),
        "alignmentReport": str(alignment_path.relative_to(project)),
        "captionTimeline": str(caption_path.relative_to(project)),
        "sceneTimeline": str(scene_path.relative_to(project)),
        "subtitleFile": str(subtitle_path.relative_to(project)),
        "alignmentReportSha256": sha256(alignment_path),
        "captionTimelineSha256": sha256(caption_path),
        "sceneTimelineSha256": sha256(scene_path),
        "subtitleSha256": sha256(subtitle_path),
        "caseSha256": sha256(case_path),
        "renderManifestSha256": sha256(manifest_path),
        "audioMix": "renders/audio_mix.m4a",
        "video": "renders/video.mp4",
        "videoSha256": video_hash,
        "scenes": scenes,
    }
    (project / "build_report.json").write_text(
        json.dumps(build_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    refresh_human_review(project, video_hash)
    print(
        json.dumps(
            {
                "status": "rendered-pending-human-review",
                "video": str(output_video),
                "frames": total_frames,
                "durationSeconds": round(duration, 3),
                "sha256": video_hash,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
