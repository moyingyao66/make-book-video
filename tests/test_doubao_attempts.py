#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import doubao_tts  # noqa: E402


class DoubaoAttemptTests(unittest.TestCase):
    def test_retry_count_is_distinct_from_logical_request_count(self) -> None:
        success = {
            "requestId": "replaced-by-wrapper",
            "xTtLogid": "log-success",
            "httpStatus": 200,
            "words": [],
            "metadataEvents": [],
        }
        with patch.object(
            doubao_tts,
            "request_once",
            side_effect=[requests.ConnectionError("temporary"), (b"wav", success)],
        ) as request, patch.object(doubao_tts.time, "sleep"):
            audio, report = doubao_tts.request_with_retry(
                "secret",
                "text",
                ".wav",
                "resource",
                "speaker",
                20,
                24000,
                retries=3,
            )

        self.assertEqual(audio, b"wav")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(report["attemptCount"], 2)
        self.assertEqual(
            [item["status"] for item in report["attempts"]],
            ["failed", "succeeded"],
        )
        self.assertNotEqual(
            report["attempts"][0]["requestId"],
            report["attempts"][1]["requestId"],
        )


if __name__ == "__main__":
    unittest.main()
