#!/usr/bin/env python3

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_case import validate_caption_contract, validate_case  # noqa: E402


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
        case["segments"] = [segment(1, "scene-1", "body", "甲。")]
        case["timelineHolds"] = []
        case["claims"] = []
        self.assertEqual(validate_case(case, require_approved=True), [])

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
