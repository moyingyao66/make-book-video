#!/usr/bin/env python3
"""Initialize a portable make-book-video project without overwriting existing work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"


def write_new_json(source: Path, target: Path, transform=None) -> None:
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {target}")
    document = json.loads(source.read_text(encoding="utf-8"))
    if transform:
        transform(document)
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", action="append", default=[])
    args = parser.parse_args()

    project = args.project.resolve()
    control_targets = [
        project / "case.json",
        project / "render-manifest.json",
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
        reveal = f"《{args.title}》。"
        if args.author:
            reveal = f"{args.author[0]}的《{args.title}》。"
        for segment in document.get("segments") or []:
            if segment.get("id") == "book-reveal":
                segment["narration"] = reveal
                captions = segment.get("captions") or []
                if captions:
                    captions[0]["zhText"] = reveal
                break

    write_new_json(ASSETS_DIR / "case-template.json", project / "case.json", configure_case)
    write_new_json(
        ASSETS_DIR / "render-manifest-template.json", project / "render-manifest.json"
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
    print(json.dumps({"status": "ok", "project": str(project)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
