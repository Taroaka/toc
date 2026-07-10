from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from server import image_gen
from toc.image_request_snapshot import (
    load_request_snapshot,
    materialize_request_snapshot,
    write_request_snapshot_atomic,
)


class ImagePromptUpdateContractTests(unittest.TestCase):
    def test_compiled_v2_prompt_update_is_rejected_before_markdown_write(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- prompt_policy_version: `image_api_prompt_v2`
- output: `assets/scenes/scene01.png`
- references: `[]`

```debug_prompt_source
drawable_prompt_ir:
  included_fragments: [current_moment]
```

```api_prompt
old compiled provider prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(request_text, encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                r"manual_prompt_update_rejected_for_compiled_v2.*plan.*manifest.*recompil",
            ):
                image_gen.update_request_prompts(
                    run_dir,
                    "scene",
                    {"scene1_cut1": "unsafe direct replacement"},
                )

            self.assertEqual(request_path.read_text(encoding="utf-8"), request_text)

    def test_compiled_v2_rejection_preserves_existing_snapshot_validity(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- prompt_policy_version: `image_api_prompt_v2`
- output: `assets/scenes/scene01.png`
- references: `[]`

```debug_prompt_source
api_prompt_payload:
  compiler_version: conditional_drawable_prompt_compiler_v1
  source_digest: preserved
drawable_prompt_ir:
  included_fragments: [current_moment]
```

```api_prompt
old compiled provider prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            snapshot_path = run_dir / "image_generation_request_snapshot.json"
            request_path.write_text(request_text, encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": "scene1_cut1",
                        "destination": "assets/scenes/scene01.png",
                        "prompt": "old compiled provider prompt",
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": "conditional_drawable_prompt_compiler_v1",
                        "source_digest": hashlib.sha256(b"first-frame-plan").hexdigest(),
                        "references": [],
                    }
                ],
                source_artifact=request_path.name,
                created_at="2026-07-10T00:00:00+09:00",
            )
            write_request_snapshot_atomic(snapshot_path, snapshot, run_dir=run_dir)
            original_snapshot_bytes = snapshot_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "manual_prompt_update_rejected_for_compiled_v2"):
                image_gen.update_request_prompts(
                    run_dir,
                    "scene",
                    {"scene1_cut1": "unsafe direct replacement"},
                )

            self.assertEqual(request_path.read_text(encoding="utf-8"), request_text)
            self.assertEqual(snapshot_path.read_bytes(), original_snapshot_bytes)
            reloaded = load_request_snapshot(snapshot_path, run_dir=run_dir)
            self.assertEqual(reloaded.request_revision, snapshot.request_revision)
            self.assertEqual(
                image_gen.load_request_items(run_dir, "scene")[0].prompt,
                "old compiled provider prompt",
            )

    def test_mixed_update_with_v2_item_rejects_all_changes(self) -> None:
        request_text = """# Image Generation Requests

## legacy_item

- prompt_policy_version: `image_api_prompt_v1`
- output: `assets/scenes/legacy.png`

```api_prompt
old legacy prompt
```

## compiled_item

- prompt_policy_version: `image_api_prompt_v2`
- output: `assets/scenes/compiled.png`

```api_prompt
old compiled prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(request_text, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "compiled_item"):
                image_gen.update_request_prompts(
                    run_dir,
                    "scene",
                    {
                        "legacy_item": "new legacy prompt",
                        "compiled_item": "unsafe compiled prompt",
                    },
                )

            self.assertEqual(request_path.read_text(encoding="utf-8"), request_text)

    def test_v1_named_prompt_update_rematerializes_existing_snapshot(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- prompt_policy_version: `image_api_prompt_v1`
- output: `assets/scenes/scene01.png`
- references: `[]`

```debug_prompt_source
review notes remain unchanged
```

```api_prompt
old v1 provider prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            snapshot_path = run_dir / "image_generation_request_snapshot.json"
            request_path.write_text(request_text, encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": "scene1_cut1",
                        "destination": "assets/scenes/scene01.png",
                        "prompt": "old v1 provider prompt",
                        "prompt_policy_version": "image_api_prompt_v1",
                        "compiler_version": "legacy_prompt_compiler_v1",
                        "source_digest": hashlib.sha256(b"legacy-source").hexdigest(),
                        "references": [],
                    }
                ],
                source_artifact=request_path.name,
                created_at="2026-07-10T00:00:00+09:00",
            )
            write_request_snapshot_atomic(snapshot_path, snapshot, run_dir=run_dir)

            result = image_gen.update_request_prompts(
                run_dir,
                "scene",
                {"scene1_cut1": "new v1 provider prompt"},
            )

            updated_text = request_path.read_text(encoding="utf-8")
            updated_snapshot = load_request_snapshot(snapshot_path, run_dir=run_dir)
            self.assertEqual(result, {"updated": ["scene1_cut1"], "missing": []})
            self.assertIn("```api_prompt\nnew v1 provider prompt\n```", updated_text)
            self.assertIn("review notes remain unchanged", updated_text)
            self.assertNotEqual(updated_snapshot.request_revision, snapshot.request_revision)
            self.assertEqual(updated_snapshot.items[0].prompt, "new v1 provider prompt")
            self.assertEqual(updated_snapshot.items[0].compiler_version, "legacy_prompt_compiler_v1")

    def test_legacy_text_fence_update_remains_supported(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- output: `assets/scenes/scene01.png`

```text
old legacy prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(request_text, encoding="utf-8")

            result = image_gen.update_request_prompts(
                run_dir,
                "scene",
                {"scene1_cut1": "new legacy prompt"},
            )

            self.assertEqual(result, {"updated": ["scene1_cut1"], "missing": []})
            self.assertIn("```text\nnew legacy prompt\n```", request_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
