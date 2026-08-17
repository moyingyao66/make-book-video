#!/usr/bin/env python3
"""Initialize a portable make-book-video project without overwriting existing work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
OPENING_SOURCE_CHOICES = ("pexels-video", "gpt-image")
BODY_SOURCE_CHOICES = ("gpt-image", "pexels-video")
BODY_VISUAL_ROLES = {
    "audience-problem",
    "alternative-explanation",
    "concrete-example",
    "practical-boundary",
    "audience-close",
}


def write_new_json(source: Path, target: Path, transform=None) -> dict:
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {target}")
    document = json.loads(source.read_text(encoding="utf-8"))
    if transform:
        transform(document)
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return document


def materialize_scene_source(spec: dict, scene_id: str, source: str) -> None:
    for field in ("loop", "motion", "sourceRecord", "startSeconds"):
        spec.pop(field, None)
    spec["fit"] = "cover"
    if source == "pexels-video":
        spec.update(
            {
                "type": "video",
                "path": f"assets/pexels/{scene_id}.mp4",
                "loop": True,
                "sourceProvider": "pexels",
                "sourceRecord": f"assets/pexels/{scene_id}-source.json",
                "assetStatus": "pending-search-frame-review-and-attribution",
            }
        )
    else:
        spec.update(
            {
                "type": "image",
                "path": f"visuals/{scene_id}.png",
                "motion": "slow-zoom",
                "sourceProvider": "gpt-image",
                "assetStatus": "pending-semantic-review",
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", action="append", default=[])
    parser.add_argument(
        "--opening-source",
        required=True,
        choices=OPENING_SOURCE_CHOICES,
        help="confirmed startup selection for the fixed opening",
    )
    parser.add_argument(
        "--body-source",
        required=True,
        choices=BODY_SOURCE_CHOICES,
        help="confirmed startup selection for narrated body scenes",
    )
    args = parser.parse_args()

    project = args.project.resolve()
    control_targets = [
        project / "case.json",
        project / "render-manifest.json",
        project / "editable-delivery.json",
        project / "renders/qa/human-review.json",
    ]
    existing = [str(path) for path in control_targets if path.exists()]
    if existing:
        raise SystemExit(
            "Refusing partial initialization because control files already exist: "
            + ", ".join(existing)
        )
    project.mkdir(parents=True, exist_ok=True)
    for directory in (
        "audio",
        "assets/covers",
        "assets/pexels",
        "assets/stock",
        "assets/music",
        "assets/sfx",
        "visuals",
        "timing",
        "renders/qa",
        "output",
    ):
        (project / directory).mkdir(parents=True, exist_ok=True)

    def configure_case(document: dict) -> None:
        document["book"]["title"] = args.title
        document["book"]["authors"] = args.author
        document["visualSourcePolicy"].update(
            {
                "selectionStatus": "confirmed",
                "selectionMethod": "request_user_input",
                "selectedAtProjectStart": True,
                "openingSource": args.opening_source,
                "bodySource": args.body_source,
                "silentFallbackAllowed": False,
            }
        )
        reveal = f"《{args.title}》。"
        if args.author:
            reveal = f"{args.author[0]}的《{args.title}》。"
        for segment in document.get("segments") or []:
            role = str(segment.get("role") or "")
            scene_id = str(segment.get("id") or "")
            if role == "fixed-opening":
                segment["asset"] = (
                    f"assets/pexels/{scene_id}.mp4"
                    if args.opening_source == "pexels-video"
                    else f"visuals/{scene_id}.png"
                )
            elif role in BODY_VISUAL_ROLES:
                segment["asset"] = (
                    f"assets/pexels/{scene_id}.mp4"
                    if args.body_source == "pexels-video"
                    else f"visuals/{scene_id}.png"
                )
            if segment.get("id") == "book-reveal":
                segment["narration"] = reveal
                captions = segment.get("captions") or []
                if captions:
                    captions[0]["zhText"] = reveal

    def configure_manifest(document: dict) -> None:
        scene_assets = document.get("sceneAssets") or {}
        for segment in case_document.get("segments") or []:
            scene_id = str(segment.get("id") or "")
            role = str(segment.get("role") or "")
            spec = scene_assets.get(scene_id)
            if not isinstance(spec, dict):
                continue
            if role == "fixed-opening":
                materialize_scene_source(spec, scene_id, args.opening_source)
            elif role in BODY_VISUAL_ROLES:
                materialize_scene_source(spec, scene_id, args.body_source)

    def write_pexels_record(scene_id: str, visual_intent: str) -> None:
        target = project / f"assets/pexels/{scene_id}-source.json"

        def configure_record(document: dict) -> None:
            document["sceneId"] = scene_id
            document["visualIntent"] = visual_intent
            document["downloadedFile"]["path"] = f"assets/pexels/{scene_id}.mp4"

        write_new_json(ASSETS_DIR / "pexels-source-template.json", target, configure_record)

    case_document = write_new_json(
        ASSETS_DIR / "case-template.json", project / "case.json", configure_case
    )
    write_new_json(
        ASSETS_DIR / "render-manifest-template.json",
        project / "render-manifest.json",
        configure_manifest,
    )
    for segment in case_document.get("segments") or []:
        role = str(segment.get("role") or "")
        selected_source = (
            args.opening_source
            if role == "fixed-opening"
            else args.body_source if role in BODY_VISUAL_ROLES else ""
        )
        if selected_source == "pexels-video":
            write_pexels_record(
                str(segment.get("id") or ""), str(segment.get("visualIntent") or "")
            )
    write_new_json(
        ASSETS_DIR / "editable-delivery-template.json",
        project / "editable-delivery.json",
    )
    write_new_json(
        ASSETS_DIR / "human-review-template.json",
        project / "renders/qa/human-review.json",
    )
    research = project / "research.md"
    if not research.exists():
        research.write_text(
            f"# {args.title} research\n\n"
            "## Research route\n\n"
            "- Primary: weread-skills\n"
            "- Skill version:\n"
            "- bookId:\n"
            "- Captured inputs: book info, chapter directory, popular highlights, public reviews\n"
            "- Private notes used: no\n"
            "- Fallback sources and reasons: none\n\n"
            "## Book identity and cover\n\n"
            "- Edition and sources:\n"
            "- Cover source and checksum:\n\n"
            "## Reader situations and reactions\n\n"
            "- Recurring concrete situations:\n"
            "- Positive reaction clusters:\n"
            "- Objection clusters:\n\n"
            "## Narrative decision\n\n"
            "- Audience:\n"
            "- Selected single thesis:\n"
            "- Supporting examples:\n"
            "- Claim boundary and omitted claims:\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "project": str(project),
                "visualSourcePolicy": {
                    "openingSource": args.opening_source,
                    "bodySource": args.body_source,
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
