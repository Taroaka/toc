from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_assets_from_manifest_credit", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestKlingCreditLogging(unittest.TestCase):
    def test_extract_kling_credit_summary_reads_final_unit_deduction(self) -> None:
        submit = {
            "data": {
                "task_id": "task_123",
            }
        }
        operation = {
            "data": {
                "task_status": "succeed",
                "task_result": {
                    "final_unit_deduction": "3.6",
                    "videos": [{"url": "https://example.com/video.mp4"}],
                },
            }
        }

        summary = MODULE._extract_kling_credit_summary(
            submit=submit,
            operation=operation,
            model="kling-v3",
            duration_seconds=6,
            aspect_ratio="16:9",
            resolution="1080p",
            output="assets/videos/scene01_cut01.mp4",
        )

        self.assertEqual(summary["provider"], "kling")
        self.assertEqual(summary["model"], "kling-v3")
        self.assertEqual(summary["task_id"], "task_123")
        self.assertEqual(summary["status"], "succeed")
        self.assertEqual(summary["final_unit_deduction"], "3.6")
        self.assertEqual(summary["duration_seconds"], 6)
        self.assertEqual(summary["aspect_ratio"], "16:9")
        self.assertEqual(summary["resolution"], "1080p")
        self.assertEqual(summary["output"], "assets/videos/scene01_cut01.mp4")

