from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from toc.image_request_snapshot import (
    materialize_request_snapshot,
    sha256_file,
    write_request_snapshot_atomic,
)


SPEC = importlib.util.spec_from_file_location(
    "verify_pipeline_for_test",
    REPO_ROOT / "scripts" / "verify-pipeline.py",
)
assert SPEC is not None and SPEC.loader is not None
verify_pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_pipeline)


class VerifyPipelineImageProvenanceTests(unittest.TestCase):
    def _write_snapshot(self, run_dir: Path):
        request_path = run_dir / "image_generation_requests.md"
        request_path.write_text("# immutable provider request\n", encoding="utf-8")
        output = run_dir / "assets" / "scenes" / "scene01_cut01.png"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        prompt = "石造りの回廊に主人公が立っている。"
        snapshot = materialize_request_snapshot(
            run_dir,
            kind="scene",
            items=[
                {
                    "item_id": "scene01_cut01",
                    "destination": "assets/scenes/scene01_cut01.png",
                    "prompt": prompt,
                    "prompt_policy_version": "image_api_prompt_v2",
                    "compiler_version": "conditional_drawable_prompt_compiler_v1",
                    "source_digest": hashlib.sha256(b"scene-source").hexdigest(),
                    "references": [],
                }
            ],
            source_artifact="image_generation_requests.md",
        )
        write_request_snapshot_atomic(
            run_dir / "image_generation_request_snapshot.json",
            snapshot,
            run_dir=run_dir,
        )
        return snapshot, snapshot.items[0], output

    def test_weak_jsonl_cannot_satisfy_v2_snapshot_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _snapshot, item, output = self._write_snapshot(run_dir)
            weak_log = run_dir / "logs" / "image_generation_prompts.jsonl"
            weak_log.parent.mkdir(parents=True)
            weak_log.write_text(
                json.dumps(
                    {
                        "itemId": item.item_id,
                        "destination": item.destination,
                        "status": "completed",
                        "source": "app_server",
                        "savedPath": str(output),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            failures = verify_pipeline._strict_snapshot_provenance_failures(
                run_dir,
                kind="scene",
                expected_outputs=[item.destination],
            )

        self.assertEqual(len(failures), 1)
        self.assertIn("no strict request_bound_v2 provenance", failures[0])

    def test_strict_item_digest_match_ignores_old_collection_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot, item, output = self._write_snapshot(run_dir)
            output_sha256 = sha256_file(output)
            log_dir = run_dir / "logs" / "app_server" / "image_gen"
            log_dir.mkdir(parents=True)
            (log_dir / "scene01_cut01.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "itemId": item.item_id,
                        "kind": "scene",
                        "destination": item.destination,
                        "apiPromptPolicyVersion": item.prompt_policy_version,
                        "source": "app_server",
                        "outputSha256": output_sha256,
                        "provenance": {
                            "policy": "request_bound_v2",
                            "generationJobId": "job-1",
                            "itemId": item.item_id,
                            "turnId": "turn-1",
                            "promptSha256": item.prompt_sha256,
                            "referenceSha256s": [],
                            "imageGenerationItemId": "image-1",
                            "imageGenerationItemCount": 1,
                            "savedPath": str(output),
                            "destination": str(output),
                            "outputSha256": output_sha256,
                            "requestRevision": "older-collection-revision",
                            "requestDigest": item.request_digest,
                            "compilerVersion": item.compiler_version,
                            "sourceDigest": item.source_digest,
                            "authoritative": True,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            failures = verify_pipeline._strict_snapshot_provenance_failures(
                run_dir,
                kind="scene",
                expected_outputs=[item.destination],
            )

        self.assertNotEqual(snapshot.request_revision, "older-collection-revision")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
