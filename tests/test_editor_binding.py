from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_editor_plan import load_json, prepare_project, write_json  # noqa: E402

PLAN_SCRIPT = REPO / "scripts/build_editor_plan.py"
BIND_SCRIPT = REPO / "scripts/bind_editor_readback.py"
VALIDATE_SCRIPT = REPO / "scripts/validate_editable_delivery.py"


def write_png(path: Path, width: int, height: int, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(b"\x00" + bytes([value]) * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


class EditorBindingTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def fill_binding(self, project: Path, *, unknown_id: bool = False) -> dict:
        binding = load_json(project / "editor-binding.json")
        binding["projectId"] = "proj-1"
        binding["timelineId"] = "tl-1"
        binding["editorUrl"] = "openchatcut://proj-1"
        binding["readback"] = {
            "source": "openchatcut read_project + read_timeline + read_captions",
            "capturedAt": "2026-01-01T00:00:00Z",
        }
        for index, role in enumerate(sorted(binding["trackIds"])):
            binding["trackIds"][role] = f"track-{index}"
        for index, plan_id in enumerate(sorted(binding["items"])):
            for field in binding["items"][plan_id]:
                binding["items"][plan_id][field] = (
                    f"{'ghost' if unknown_id and field == 'itemId' and index == 0 else 'ed'}"
                    f"-{field}-{index}"
                )
        binding["verificationFrames"] = [
            {"frame": 1, "evidencePath": "renders/qa/editor-open.png", "notes": "opening"},
            {"frame": 15, "evidencePath": "renders/qa/editor-mid.png", "notes": "middle"},
            {"frame": 29, "evidencePath": "renders/qa/editor-end.png", "notes": "ending"},
        ]
        write_json(project / "editor-binding.json", binding)
        return binding

    def write_editor_response(self, project: Path, binding: dict) -> None:
        ids = list(binding["trackIds"].values())
        for entry in binding["items"].values():
            ids.extend(entry.values())
        write_json(
            project / "renders/qa/editor-response.json",
            {
                "projectId": binding["projectId"],
                "timelineId": binding["timelineId"],
                "returnedIds": sorted(set(ids)),
            },
        )

    def prepare(self, project: Path) -> dict:
        prepare_project(project)
        plan = self.run_script(PLAN_SCRIPT, str(project))
        self.assertEqual(plan.returncode, 0, plan.stderr)
        for name in ("editor-open", "editor-mid", "editor-end"):
            write_png(project / f"renders/qa/{name}.png", 1080, 1920, hash(name) % 200)
        template = self.run_script(
            BIND_SCRIPT, str(project), "--emit-binding-template"
        )
        self.assertEqual(template.returncode, 0, template.stderr)
        return self.fill_binding(project)

    def test_binding_produces_a_delivery_that_passes_the_validator(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "book"
            binding = self.prepare(project)
            self.write_editor_response(project, binding)
            bound = self.run_script(
                BIND_SCRIPT,
                str(project),
                "--editor-response",
                "renders/qa/editor-response.json",
                "--status",
                "verified",
            )
            self.assertEqual(bound.returncode, 0, bound.stderr)
            summary = json.loads(bound.stdout)
            self.assertEqual(summary["status"], "verified")
            self.assertEqual(summary["sceneItems"], 4)
            self.assertEqual(summary["captionItems"], 3)

            delivery = load_json(project / "editable-delivery.json")
            caption = delivery["assembly"]["captionItems"][0]
            self.assertEqual(caption["zhText"], "甲。")
            self.assertTrue(caption["editable"])
            self.assertEqual(
                delivery["readback"]["evidencePath"], "renders/qa/editor-readback.json"
            )

            checked = self.run_script(VALIDATE_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertTrue(json.loads(checked.stdout)["ok"])

    def test_verified_status_requires_a_recorded_editor_response(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "book"
            self.prepare(project)
            bound = self.run_script(BIND_SCRIPT, str(project), "--status", "verified")
            self.assertEqual(bound.returncode, 1)
            self.assertIn("--editor-response", bound.stderr)
            self.assertFalse((project / "editable-delivery.json").exists())

    def test_ids_absent_from_the_editor_response_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "book"
            binding = self.prepare(project)
            self.write_editor_response(project, binding)
            self.fill_binding(project, unknown_id=True)
            bound = self.run_script(
                BIND_SCRIPT,
                str(project),
                "--editor-response",
                "renders/qa/editor-response.json",
                "--status",
                "verified",
            )
            self.assertEqual(bound.returncode, 1)
            self.assertIn("do not appear in any recorded editor response", bound.stderr)

    def test_stale_plan_is_rejected_before_binding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "book"
            binding = self.prepare(project)
            self.write_editor_response(project, binding)
            case = load_json(project / "case.json")
            case["segments"][0]["narration"] = "改动。"
            write_json(project / "case.json", case)
            bound = self.run_script(
                BIND_SCRIPT,
                str(project),
                "--editor-response",
                "renders/qa/editor-response.json",
            )
            self.assertEqual(bound.returncode, 1)
            self.assertIn("rerun scripts/build_editor_plan.py", bound.stderr)

    def test_missing_plan_id_is_reported_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw) / "book"
            binding = self.prepare(project)
            self.write_editor_response(project, binding)
            binding["items"].pop("caption-0000")
            write_json(project / "editor-binding.json", binding)
            bound = self.run_script(
                BIND_SCRIPT,
                str(project),
                "--editor-response",
                "renders/qa/editor-response.json",
            )
            self.assertEqual(bound.returncode, 1)
            self.assertIn("caption-0000", bound.stderr)


if __name__ == "__main__":
    unittest.main()
