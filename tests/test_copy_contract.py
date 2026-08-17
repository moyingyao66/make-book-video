#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_case import (  # noqa: E402
    validate_caption_contract,
    validate_case,
    validate_pexels_source_record,
    validate_visual_source_contract,
)


def segment(index: int, segment_id: str, role: str, narration: str, claims=None) -> dict:
    return {
        "id": segment_id,
        "role": role,
        "narration": narration,
        "visualIntent": "test intent",
        "asset": f"visuals/{segment_id}.png",
        "sourceClaimIds": claims or [],
        "captions": [
            {
                "id": f"caption-{index:03d}",
                "zhText": narration,
                "enText": "",
            }
        ],
    }


def valid_copy_case() -> dict:
    segments = [
        segment(1, "intro", "fixed-opening", "今天分享的是。"),
        segment(2, "book-reveal", "book-reveal", "丹尼尔·卡尼曼的《思考，快与慢》。"),
        segment(
            3,
            "audience-problem",
            "audience-problem",
            "你有没有过这样的时刻：面试时聊得很投机，当场就觉得这份工作适合自己。入职后才发现，薪资、成长空间和工作方式，你几乎都没认真比较。",
        ),
        segment(
            4,
            "alternative-explanation",
            "alternative-explanation",
            "这本书给了另一种解释：系统一凭直觉快速作答，系统二本该核对，却费力又容易偷懒，常常只替第一个答案找理由。",
            ["claim-systems"],
        ),
        segment(
            5,
            "concrete-example",
            "concrete-example",
            "衣服原价一千、现价五百，你会觉得捡了便宜；可如果没见过原价，你还觉得它值五百吗？这就是锚定。更隐蔽的是，我们会把难题悄悄换掉。“这份工作长期适合我吗”，变成“我喜不喜欢面试官”。问题没回答，结论却已经有了。",
            ["claim-anchor", "claim-substitution"],
        ),
        segment(
            6,
            "practical-boundary",
            "practical-boundary",
            "所以，金额很大、代价不可逆，或者你异常确信时，先慢一下：拿掉最初的数字，再问自己，我回答的还是原来的问题吗？这本书不太好读。别急着硬啃，带着一个真实决定去读相关章节，反而更容易看见自己的判断漏洞。",
            ["claim-pause"],
        ),
        segment(
            7,
            "audience-close",
            "audience-close",
            "如果你总在决定之后才发现自己被第一印象带着走，这本书最值得带走的，就是这个停顿：答案来得越快，越要多检查一次。",
        ),
    ]
    claims = [
        {
            "id": "claim-systems",
            "category": "attributed",
            "text": "The book describes fast and effortful modes of thinking.",
            "sourceUrl": "https://weread.qq.com/example",
        },
        {
            "id": "claim-anchor",
            "category": "attributed",
            "text": "The book discusses anchoring.",
            "sourceUrl": "https://weread.qq.com/example",
        },
        {
            "id": "claim-substitution",
            "category": "attributed",
            "text": "The book discusses question substitution.",
            "sourceUrl": "https://weread.qq.com/example",
        },
        {
            "id": "claim-pause",
            "category": "interpretation",
            "text": "A practical pause derived from the book framework.",
            "sourceUrl": "research.md",
        },
    ]
    return {
        "version": 2,
        "status": "approved",
        "inputMode": "book-title",
        "narrativeProfile": {
            "id": "cognition-awakening-v1",
            "targetCharacters": {"min": 350, "max": 420},
            "planningSeconds": {"min": 80, "max": 95},
            "introSegmentId": "intro",
            "fixedOpening": "今天分享的是。",
            "carouselHoldId": "anticipation-carousel",
            "carouselFrames": 45,
            "bookRevealSegmentId": "book-reveal",
        },
        "researchRoute": {
            "primary": "weread-skills",
            "skillVersion": "1.0.4",
            "status": "captured",
            "bookId": "573975",
            "capturedInputs": [
                "/book/info",
                "/book/chapterinfo",
                "/book/bestbookmarks",
                "/review/list",
            ],
            "privateNotesUsed": False,
            "fallbacks": [],
        },
        "book": {
            "title": "思考，快与慢",
            "authors": ["丹尼尔·卡尼曼"],
        },
        "audience": "容易被第一印象带着走的决策者",
        "angle": "答案来得越快，越要检查原问题",
        "claims": claims,
        "copyReview": {
            "status": "completed",
            "reviewedBy": "editorial-review",
            "checks": {
                "singleMainThesis": True,
                "audienceSituationConcrete": True,
                "bookEvidenceMapped": True,
                "examplesServeThesis": True,
                "endingReturnsToAudience": True,
                "readAloudNatural": True,
            },
        },
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "voice": {
            "resourceId": "seed-tts-2.0",
            "speaker": "zh_male_cixingjieshuonan_uranus_bigtts",
            "speechRate": 20,
            "enableSubtitle": True,
            "requireSingleProviderRequest": True,
        },
        "segments": segments,
        "timelineHolds": [
            {
                "id": "anticipation-carousel",
                "afterSegmentId": "intro",
                "durationFrames": 45,
                "requiresVerifiedPcmSilence": True,
            }
        ],
        "approval": {
            "contentApprovedByUser": True,
            "storyboardApprovedByUser": True,
            "paidGenerationAuthorized": True,
        },
    }


def version_three_visual_fixture(
    opening_source: str = "pexels-video", body_source: str = "gpt-image"
) -> tuple[dict, dict]:
    case = valid_copy_case()
    case["version"] = 3
    case["visualSourcePolicy"] = {
        "selectionStatus": "confirmed",
        "selectionMethod": "host-structured-choice",
        "selectedAtProjectStart": True,
        "openingSource": opening_source,
        "bodySource": body_source,
        "silentFallbackAllowed": False,
    }
    body_roles = {
        "audience-problem",
        "alternative-explanation",
        "concrete-example",
        "practical-boundary",
        "audience-close",
    }
    scene_assets = {}
    for item in case["segments"]:
        scene_id = item["id"]
        role = item["role"]
        if role == "fixed-opening":
            source = opening_source
        elif role in body_roles:
            source = body_source
        else:
            continue
        if source == "pexels-video":
            path = f"assets/pexels/{scene_id}.mp4"
            scene_assets[scene_id] = {
                "type": "video",
                "path": path,
                "sourceProvider": "pexels",
                "sourceRecord": f"assets/pexels/{scene_id}-source.json",
            }
        else:
            path = f"visuals/{scene_id}.png"
            scene_assets[scene_id] = {
                "type": "image",
                "path": path,
                "sourceProvider": "gpt-image",
            }
        item["asset"] = path
    return case, {"sceneAssets": scene_assets}


class CopyContractTests(unittest.TestCase):
    def test_valid_default_profile_passes(self) -> None:
        self.assertEqual(validate_case(valid_copy_case(), require_approved=True), [])

    def test_conceptual_hook_before_fixed_opening_fails(self) -> None:
        case = valid_copy_case()
        case["segments"][0]["narration"] = "影响你决定的可能是第一个数字。"
        case["segments"][0]["captions"][0]["zhText"] = case["segments"][0]["narration"]
        errors = validate_case(case, require_approved=False)
        self.assertTrue(any("must say exactly" in error for error in errors), errors)

    def test_title_first_route_requires_captured_weread(self) -> None:
        case = valid_copy_case()
        case["researchRoute"]["status"] = "pending"
        errors = validate_case(case, require_approved=False)
        self.assertTrue(any("captured WeRead research" in error for error in errors), errors)

    def test_book_page_route_uses_the_same_research_contract(self) -> None:
        case = valid_copy_case()
        case["inputMode"] = "book-page"
        case["researchRoute"]["status"] = "pending"
        errors = validate_case(case, require_approved=False)
        self.assertTrue(
            any("book-page input requires captured WeRead research" in error for error in errors),
            errors,
        )

    def test_title_first_route_allows_only_a_documented_weread_fallback(self) -> None:
        case = valid_copy_case()
        route = case["researchRoute"]
        route.update(
            {
                "status": "unavailable-with-fallback",
                "bookId": "",
                "capturedInputs": ["weread search attempted; unavailable"],
                "fallbacks": [
                    {
                        "sourceUrl": "https://example.com/attributable-book-page",
                        "reason": "WeRead returned no matching edition",
                    }
                ],
            }
        )
        self.assertEqual(validate_case(case, require_approved=False), [])

        route["fallbacks"] = []
        errors = validate_case(case, require_approved=False)
        self.assertTrue(any("fallbacks must document" in error for error in errors), errors)

        route["fallbacks"] = [
            {"sourceUrl": "publisher page", "reason": "WeRead unavailable"}
        ]
        errors = validate_case(case, require_approved=False)
        self.assertTrue(any("HTTP(S) URL" in error for error in errors), errors)

        case["narrativeProfile"] = {"id": "custom"}
        errors = validate_case(case, require_approved=False)
        self.assertTrue(
            any("HTTP(S) URL" in error for error in errors),
            "declared fallbacks must remain validated for custom profiles",
        )

    def test_structured_visual_choice_rejects_tool_specific_or_free_text_methods(self) -> None:
        case, manifest = version_three_visual_fixture()
        case["status"] = "draft"
        self.assertEqual(
            validate_case(case, require_approved=False, manifest=manifest), []
        )
        for unsupported in ("request_user_input", "free-text", "manual"):
            case["visualSourcePolicy"]["selectionMethod"] = unsupported
            errors = validate_case(case, require_approved=False, manifest=manifest)
            self.assertTrue(
                any("host-structured-choice" in error for error in errors), errors
            )

    def test_declared_length_range_is_enforced(self) -> None:
        case = valid_copy_case()
        case["narrativeProfile"]["targetCharacters"] = {"min": 700, "max": 800}
        errors = validate_case(case, require_approved=False)
        self.assertTrue(any("declared range" in error for error in errors), errors)

    def test_copy_review_must_be_completed(self) -> None:
        case = valid_copy_case()
        case["copyReview"]["checks"]["readAloudNatural"] = False
        errors = validate_case(case, require_approved=False)
        self.assertIn("copyReview.checks.readAloudNatural must be true", errors)

    def test_custom_profile_keeps_generic_pipeline_available(self) -> None:
        case = valid_copy_case()
        case["narrativeProfile"] = {"id": "custom"}
        case["segments"] = [
            segment(1, "scene-1", "body", "甲。", ["claim-systems"])
        ]
        case["timelineHolds"] = []
        self.assertEqual(validate_case(case, require_approved=True), [])

    def test_custom_profile_cannot_bypass_evidence_or_copy_review(self) -> None:
        case = valid_copy_case()
        case["narrativeProfile"] = {"id": "custom"}
        case["segments"] = [segment(1, "scene-1", "body", "甲。")]
        case["claims"] = []
        case["copyReview"]["status"] = "pending"
        errors = validate_case(case, require_approved=False)
        self.assertTrue(any("source-checked claims" in error for error in errors), errors)
        self.assertTrue(any("must map its substantial content" in error for error in errors), errors)
        self.assertIn("copyReview.status must be completed before approval", errors)

    def test_preserved_script_uses_the_same_evidence_contract(self) -> None:
        case = valid_copy_case()
        case["narrativeProfile"] = {"id": "preserve-approved-script"}
        case["segments"] = [
            segment(1, "scene-1", "body", "保留这句话。", ["claim-systems"])
        ]
        case["timelineHolds"] = []
        self.assertEqual(validate_case(case, require_approved=True), [])

    def test_version_three_requires_startup_visual_selections(self) -> None:
        case = valid_copy_case()
        case["version"] = 3
        errors = validate_case(case, require_approved=True)
        self.assertIn("visualSourcePolicy is required for version 3 projects", errors)

    def test_structured_visual_policy_matches_materialized_manifest(self) -> None:
        case, manifest = version_three_visual_fixture()
        case["status"] = "draft"
        self.assertEqual(validate_case(case, require_approved=False), [])
        self.assertEqual(validate_visual_source_contract(case, manifest), [])

    def test_visual_policy_rejects_silent_source_substitution(self) -> None:
        case, manifest = version_three_visual_fixture(
            opening_source="gpt-image", body_source="pexels-video"
        )
        manifest["sceneAssets"]["concrete-example"] = {
            "type": "image",
            "path": "visuals/concrete-example.png",
            "sourceProvider": "gpt-image",
        }
        errors = validate_visual_source_contract(case, manifest)
        self.assertTrue(any("concrete-example must use type video" in item for item in errors), errors)
        self.assertTrue(any("sourceProvider pexels" in item for item in errors), errors)

    def test_pexels_record_requires_current_file_and_frame_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            video = project / "assets/pexels/intro.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"test-moving-video-fixture")
            digest = hashlib.sha256(video.read_bytes()).hexdigest()
            record = {
                "provider": "Pexels",
                "sceneId": "intro",
                "query": "thoughtful reader portrait",
                "pexelsPage": "https://www.pexels.com/video/example/",
                "creator": {
                    "name": "Example Creator",
                    "url": "https://www.pexels.com/@example/",
                },
                "selectedFile": {
                    "url": "https://videos.pexels.com/example.mp4",
                    "width": 1080,
                    "height": 1920,
                },
                "attribution": {
                    "linkBack": "https://www.pexels.com",
                    "text": "Video by Example Creator on Pexels",
                },
                "downloadedFile": {
                    "path": "assets/pexels/intro.mp4",
                    "sha256": digest,
                },
                "frameReview": {
                    "status": "passed",
                    "reviewedAt": "2026-01-01T00:00:00Z",
                    "positions": ["start", "middle", "end"],
                },
            }
            record_path = project / "assets/pexels/intro-source.json"
            record_path.write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
            spec = {
                "path": "assets/pexels/intro.mp4",
                "sourceRecord": "assets/pexels/intro-source.json",
            }
            self.assertEqual(
                validate_pexels_source_record(project, "intro", spec, True), []
            )
            record["downloadedFile"]["sha256"] = "0" * 64
            record_path.write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
            errors = validate_pexels_source_record(project, "intro", spec, True)
            self.assertIn("scene intro Pexels downloaded file hash is stale", errors)

    def test_bilingual_manifest_rejects_empty_english(self) -> None:
        case = valid_copy_case()
        manifest = {
            "canvas": case["canvas"],
            "captions": {
                "mode": "bilingual",
                "requireEnglish": True,
                "fontSize": 72,
                "englishFontSize": 40,
                "positionY": 1500,
                "safeBottomPx": 360,
            },
        }
        errors = validate_caption_contract(case, manifest)
        self.assertTrue(any("empty enText" in error for error in errors), errors)

    def test_caption_safe_zone_and_sizes_are_enforced(self) -> None:
        case = valid_copy_case()
        manifest = {
            "canvas": case["canvas"],
            "captions": {
                "mode": "zh-only",
                "fontSize": 58,
                "englishFontSize": 34,
                "positionY": 1850,
                "safeBottomPx": 110,
            },
        }
        errors = validate_caption_contract(case, manifest)
        self.assertTrue(any("fontSize" in error for error in errors), errors)
        self.assertTrue(any("safeBottomPx" in error for error in errors), errors)
        self.assertTrue(any("safe zone" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
