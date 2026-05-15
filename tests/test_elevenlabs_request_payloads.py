from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATE_ASSETS_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
GENERATE_TTS_PATH = REPO_ROOT / "scripts" / "generate-elevenlabs-tts.py"

SPEC = importlib.util.spec_from_file_location("generate_assets_for_elevenlabs_payloads", GENERATE_ASSETS_PATH)
assert SPEC and SPEC.loader
GENERATE_ASSETS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATE_ASSETS
SPEC.loader.exec_module(GENERATE_ASSETS)


class TestElevenLabsRequestPayloads(unittest.TestCase):
    def test_manifest_generator_request_log_includes_japanese_language_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            request_log = tmp_path / "tts_request.json"

            with contextlib.redirect_stdout(io.StringIO()):
                GENERATE_ASSETS.generate_elevenlabs_tts(
                    client=None,
                    voice_id="voice",
                    model_id="eleven_v3",
                    output_format="mp3_44100_128",
                    language_code="ja",
                    text="こんにちは",
                    out_path=tmp_path / "audio.mp3",
                    duration_seconds=None,
                    force=True,
                    request_log_path=request_log,
                    dry_run=True,
                )

            payload = json.loads(request_log.read_text(encoding="utf-8"))
            self.assertEqual(payload["language_code"], "ja")

    def test_standalone_tts_save_request_includes_japanese_language_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            request_log = tmp_path / "tts_request.json"

            subprocess.run(
                [
                    sys.executable,
                    str(GENERATE_TTS_PATH),
                    "--api-key",
                    "test_key",
                    "--text",
                    "こんにちは",
                    "--out",
                    str(tmp_path / "audio.mp3"),
                    "--save-request",
                    str(request_log),
                    "--dry-run",
                ],
                check=True,
                cwd=REPO_ROOT,
                stdout=subprocess.DEVNULL,
            )

            payload = json.loads(request_log.read_text(encoding="utf-8"))
            self.assertEqual(payload["language_code"], "ja")


if __name__ == "__main__":
    unittest.main()
