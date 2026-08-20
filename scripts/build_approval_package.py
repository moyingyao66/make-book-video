#!/usr/bin/env python3
"""Build a deterministic pre-generation approval package from project truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from validate_case import (
    non_whitespace_character_count,
    validate_caption_contract,
    validate_case,
    validate_visual_source_contract,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def clean(value: Any) -> str:
    return str(value or "").strip()


def markdown_cell(value: Any) -> str:
    return clean(value).replace("|", "\\|").replace("\n", "<br>")


def build_package(
    project: Path, case: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    profile = case.get("narrativeProfile") or {}
    research = case.get("researchRoute") or {}
    segments = case.get("segments") or []
    narration = "\n".join(clean(item.get("narration")) for item in segments)
    claims = [
        {
            "id": clean(item.get("id")),
            "category": clean(item.get("category")),
            "text": clean(item.get("text")),
            "sourceUrl": clean(item.get("sourceUrl")),
        }
        for item in case.get("claims") or []
    ]
    storyboard = [
        {
            "id": clean(item.get("id")),
            "role": clean(item.get("role")),
            "narration": clean(item.get("narration")),
            "visualIntent": clean(item.get("visualIntent")),
            "asset": clean(item.get("asset")),
            "sourceClaimIds": [clean(value) for value in item.get("sourceClaimIds") or []],
        }
        for item in segments
    ]
    return {
        "version": 1,
        "status": "ready-for-user-review",
        "contract": "make-book-video-approval-v1",
        "sourceHashes": {
            "caseSha256": sha256(project / "case.json"),
            "renderManifestSha256": sha256(project / "render-manifest.json"),
        },
        "book": case.get("book") or {},
        "audience": clean(case.get("audience")),
        "angle": clean(case.get("angle")),
        "visualSourcePolicy": case.get("visualSourcePolicy") or {},
        "visualStyleProfile": case.get("visualStyleProfile") or {},
        "narration": {
            "fullText": narration,
            "nonWhitespaceCharacters": non_whitespace_character_count(narration),
            "planningSeconds": profile.get("planningSeconds") or {},
        },
        "evidenceBoundary": {
            "primaryResearchRoute": clean(research.get("primary")),
            "researchStatus": clean(research.get("status")),
            "skillVersion": clean(research.get("skillVersion")),
            "bookId": clean(research.get("bookId")),
            "capturedInputs": research.get("capturedInputs") or [],
            "privateNotesUsed": research.get("privateNotesUsed"),
            "fallbacks": research.get("fallbacks") or [],
            "claims": claims,
        },
        "storyboard": storyboard,
        "timelineHolds": case.get("timelineHolds") or [],
        "approvalRequested": [
            "contentApprovedByUser",
            "storyboardApprovedByUser",
            "paidGenerationAuthorized",
        ],
    }


def render_markdown(package: dict[str, Any]) -> str:
    book = package.get("book") or {}
    title = clean(book.get("title"))
    authors = "、".join(clean(value) for value in book.get("authors") or []) or "未填写"
    narration = package.get("narration") or {}
    boundary = package.get("evidenceBoundary") or {}
    policy = package.get("visualSourcePolicy") or {}
    style = package.get("visualStyleProfile") or {}
    planning = narration.get("planningSeconds") or {}
    lines = [
        f"# 《{title}》生成前确认包",
        "",
        "## 请确认",
        "",
        "- [ ] 完整旁白内容",
        "- [ ] 语义分镜与素材方向",
        "- [ ] 三种同场景预览与最终视觉风格",
        "- [ ] 确认后授权完整 TTS 与批量素材生成",
        "",
        "## 项目摘要",
        "",
        f"- 作者：{authors}",
        f"- 目标观众：{clean(package.get('audience'))}",
        f"- 单一主论点：{clean(package.get('angle'))}",
        f"- 开场素材：{clean(policy.get('openingSource'))}",
        f"- 正文素材：{clean(policy.get('bodySource'))}",
        f"- 视觉风格：{clean(style.get('selectedStyleId'))}",
        f"- 人脸策略：{clean(style.get('facePolicy'))}",
        f"- 旁白字数：{narration.get('nonWhitespaceCharacters', 0)}",
        f"- 规划时长：{planning.get('min', '')}–{planning.get('max', '')} 秒；实际以豆包音频为准",
        "",
        "## 视觉风格候选",
        "",
        "| 风格 | 适配理由 | 同场景预览 |",
        "|---|---|---|",
    ]
    for candidate in style.get("candidates") or []:
        lines.append(
            "| {id} | {rationale} | {preview} |".format(
                id=markdown_cell(candidate.get("id")),
                rationale=markdown_cell(candidate.get("rationale")),
                preview=markdown_cell(candidate.get("previewPath")),
            )
        )
    lines.extend(
        [
            "",
            "## 完整旁白",
            "",
            clean(narration.get("fullText")),
            "",
            "## 证据边界",
            "",
            f"- 主研究路径：{clean(boundary.get('primaryResearchRoute'))}",
            f"- 微信读书 bookId：{clean(boundary.get('bookId'))}",
            f"- 私人笔记：{'使用' if boundary.get('privateNotesUsed') else '未使用'}",
            "",
            "| Claim | 类别 | 表述边界 | 来源 |",
            "|---|---|---|---|",
        ]
    )
    for claim in boundary.get("claims") or []:
        lines.append(
            "| {id} | {category} | {text} | {source} |".format(
                id=markdown_cell(claim.get("id")),
                category=markdown_cell(claim.get("category")),
                text=markdown_cell(claim.get("text")),
                source=markdown_cell(claim.get("sourceUrl")),
            )
        )
    lines.extend(
        [
            "",
            "## 语义分镜",
            "",
            "| 顺序 | 场景职责 | 旁白 | 画面意图 | 素材 | 证据 |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for index, item in enumerate(package.get("storyboard") or [], start=1):
        lines.append(
            "| {index} | {role} | {narration} | {intent} | {asset} | {claims} |".format(
                index=index,
                role=markdown_cell(item.get("role")),
                narration=markdown_cell(item.get("narration")),
                intent=markdown_cell(item.get("visualIntent")),
                asset=markdown_cell(item.get("asset")),
                claims=markdown_cell(", ".join(item.get("sourceClaimIds") or []) or "—"),
            )
        )
    lines.extend(
        [
            "",
            "确认并试听通过后，运行 `record_approval.py` 写入哈希绑定回执；不要手工改 `case.status` 或 `approval`。如果旁白、分镜或来源变化，重新审核。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    case = load_json(project / "case.json")
    manifest = load_json(project / "render-manifest.json")
    approval = case.get("approval")
    receipt = approval.get("receipt") if isinstance(approval, dict) else None
    if isinstance(receipt, dict) and receipt:
        print(
            json.dumps(
                {
                    "ok": False,
                    "errors": [
                        "approval is already hash-bound; do not overwrite its package. "
                        "Return the case to draft and clear the receipt before a new review cycle."
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    errors = validate_case(case, require_approved=False)
    errors.extend(validate_caption_contract(case, manifest))
    errors.extend(validate_visual_source_contract(case, manifest))
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    package = build_package(project, case, manifest)
    json_path = project / "approval-package.json"
    markdown_path = project / "approval-package.md"
    write_text_atomic(
        json_path, json.dumps(package, ensure_ascii=False, indent=2) + "\n"
    )
    write_text_atomic(markdown_path, render_markdown(package))
    print(
        json.dumps(
            {
                "ok": True,
                "json": str(json_path),
                "markdown": str(markdown_path),
                "caseSha256": package["sourceHashes"]["caseSha256"],
                "renderManifestSha256": package["sourceHashes"]["renderManifestSha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
