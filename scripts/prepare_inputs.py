#!/usr/bin/env python3
"""Validate case.json and generate pipeline inputs before TTS."""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


def normalized_chars(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in text if unicodedata.category(char)[:1] in {"L", "N"})


def validate_case(case: dict[str, Any]) -> list[str]:
    """Return a list of validation errors.  Empty means ready for TTS."""
    errors: list[str] = []

    book = case.get("book") or {}
    if not str(book.get("title") or "").strip():
        errors.append("book.title is empty")
    if not book.get("authors"):
        errors.append("book.authors is empty")

    voice = case.get("voice") or {}
    if not str(voice.get("resourceId") or "").strip():
        errors.append("voice.resourceId is empty")
    if not str(voice.get("speaker") or "").strip():
        errors.append("voice.speaker is empty")
    if voice.get("enableSubtitle") is not True:
        errors.append("voice.enableSubtitle must be true")

    segments = case.get("segments") or []
    if not segments:
        errors.append("segments is empty")
        return errors

    segment_ids: set[str] = set()
    for i, seg in enumerate(segments):
        seg_id = str(seg.get("id") or "").strip()
        if not seg_id:
            errors.append(f"segment[{i}].id is empty")
            continue
        if seg_id in segment_ids:
            errors.append(f"segment[{i}].id '{seg_id}' is duplicated")
        segment_ids.add(seg_id)

        narration = str(seg.get("narration") or seg.get("spoken_text") or "").strip()
        if not narration:
            errors.append(f"segment '{seg_id}' has no narration")
            continue

        narration_norm = normalized_chars(narration)
        if not narration_norm:
            errors.append(f"segment '{seg_id}' narration has no alignable characters")
            continue

        captions = seg.get("captions") or []
        if not captions:
            errors.append(f"segment '{seg_id}' has no captions")
            continue

        caption_norm = ""
        for j, cap in enumerate(captions):
            cap_id = str(cap.get("id") or "").strip()
            text = str(cap.get("zhText") or cap.get("text") or "").strip()
            if not text:
                errors.append(f"segment '{seg_id}' caption[{j}] ('{cap_id}') has no text")
                continue
            caption_norm += normalized_chars(text)

        if caption_norm and narration_norm != caption_norm:
            idx = 0
            limit = min(len(narration_norm), len(caption_norm))
            while idx < limit and narration_norm[idx] == caption_norm[idx]:
                idx += 1
            errors.append(
                f"segment '{seg_id}' narration/caption text mismatch at char {idx}: "
                f"narration[{idx}:+16]='{narration_norm[idx:idx + 16]}' "
                f"caption[{idx}:+16]='{caption_norm[idx:idx + 16]}' "
                f"(narration {len(narration_norm)} chars, captions {len(caption_norm)} chars)"
            )

    for hold in case.get("timelineHolds") or []:
        after_id = str(hold.get("afterSegmentId") or "")
        if after_id and after_id not in segment_ids:
            errors.append(f"timelineHold references unknown segment: '{after_id}'")
        frames = int(hold.get("durationFrames") or 0)
        if frames <= 0:
            errors.append(f"timelineHold '{hold.get('id')}' has no positive durationFrames")

    return errors


def generate_narration_text(case: dict[str, Any]) -> str:
    parts = []
    for seg in case.get("segments") or []:
        narration = str(seg.get("narration") or seg.get("spoken_text") or "").strip()
        if narration:
            parts.append(narration)
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_file", type=Path, help="Path to case.json")
    parser.add_argument("--output-dir", type=Path, help="Task directory for generated files")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't write files")
    args = parser.parse_args()

    if not args.case_file.is_file():
        print(f"FAIL: case file not found: {args.case_file}", file=sys.stderr)
        return 1

    case = json.loads(args.case_file.read_text(encoding="utf-8"))
    errors = validate_case(case)

    if errors:
        print(f"FAIL: {len(errors)} validation error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("PASS: case.json is valid for TTS pipeline")

    if args.dry_run:
        return 0

    output_dir = args.output_dir or args.case_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    narration_path = output_dir / "narration.txt"
    narration_text = generate_narration_text(case)
    narration_path.write_text(narration_text, encoding="utf-8")
    print(f"  wrote {narration_path} ({len(narration_text)} chars)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
