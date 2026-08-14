#!/usr/bin/env python3
"""Search optional portrait stock footage through the official Pexels API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.pexels.com/v1/videos/search"


def best_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        item
        for item in files
        if item.get("link") and item.get("file_type") in {None, "video/mp4"}
    ]
    if not candidates:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int, float, int]:
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        ratio = width / height if height else 1.0
        return (
            1 if height > width else 0,
            1 if width >= 720 and height >= 1280 else 0,
            -abs(ratio - 9 / 16),
            -(abs(width - 1080) + abs(height - 1920)),
        )

    selected = max(candidates, key=score)
    return {
        "id": selected.get("id"),
        "quality": selected.get("quality"),
        "fileType": selected.get("file_type"),
        "width": selected.get("width"),
        "height": selected.get("height"),
        "fps": selected.get("fps"),
        "link": selected.get("link"),
    }


def normalize(video: dict[str, Any]) -> dict[str, Any]:
    creator = video.get("user") or {}
    return {
        "id": video.get("id"),
        "durationSeconds": video.get("duration"),
        "pexelsPage": video.get("url"),
        "previewImage": video.get("image"),
        "creator": {"name": creator.get("name"), "url": creator.get("url")},
        "bestFile": best_file(video.get("video_files") or []),
    }


def search(query: str, page: int, per_page: int, timeout: float) -> dict[str, Any]:
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is missing; Pexels is optional and may be replaced")
    params = urllib.parse.urlencode(
        {
            "query": query,
            "orientation": "portrait",
            "size": "medium",
            "page": page,
            "per_page": per_page,
        }
    )
    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={
            "Authorization": api_key,
            "Accept": "application/json",
            "User-Agent": "make-book-video/1.0",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        payload = json.load(response)
        rate_limit = {
            "limit": response.headers.get("X-Ratelimit-Limit"),
            "remaining": response.headers.get("X-Ratelimit-Remaining"),
            "reset": response.headers.get("X-Ratelimit-Reset"),
        }
    return {
        "source": "Pexels API",
        "query": query,
        "orientation": "portrait",
        "size": "medium",
        "page": payload.get("page", page),
        "totalResults": payload.get("total_results"),
        "rateLimit": rate_limit,
        "attribution": {
            "linkBack": "https://www.pexels.com",
            "rule": "Save the selected Pexels page and creator attribution.",
        },
        "candidates": [normalize(item) for item in payload.get("videos") or []],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="book")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--per-page", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.page < 1 or not 1 <= args.per_page <= 80:
        parser.error("invalid page or per-page value")
    try:
        report = search(args.query, args.page, args.per_page, args.timeout)
    except RuntimeError as exc:
        print(json.dumps({"status": "optional-source-unavailable", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except urllib.error.HTTPError as exc:
        print(json.dumps({"status": "api-error", "httpStatus": exc.code}, ensure_ascii=False), file=sys.stderr)
        return 3
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "network-error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
