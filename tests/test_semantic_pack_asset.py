import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_asset import collect_entries


def _write_asset_fixture(run_dir: Path) -> None:
    (run_dir / "asset_inventory.md").write_text(
        """# Asset Inventory

```yaml
asset_inventory:
  source_artifacts: ["story.md", "script.md", "video_manifest.md"]
  coverage_scope:
    characters: ["cinderella_fullbody"]
    story_specific_items: ["glass_slipper"]
    locations: ["ballroom"]
    setpieces: []
    reusable_stills: []
  items:
    - item_id: "cinderella_fullbody"
      category: "character"
      source_script_selectors: ["scene01_cut01"]
      story_purpose: "舞踏会前後で同一人物として見えるための基準参照"
      reusable_reason: "Cinderella の visual identity を固定する"
      recommended_asset_type: "character_reference"
    - item_id: "glass_slipper"
      category: "object"
      source_script_selectors: ["scene03_cut02"]
      story_purpose: "王子が探す物語固有アイテム"
      reusable_reason: "ガラスの靴を正しい場面だけで参照する"
      recommended_asset_type: "object_reference"
```
""",
        encoding="utf-8",
    )
    (run_dir / "asset_plan.md").write_text(
        """# Asset Plan

```yaml
asset_plan_metadata:
  topic: "シンデレラ"
review_contract:
  must_cover:
    - "主要人物と物語固有アイテムを網羅する"
assets:
  characters:
    - asset_id: "cinderella_fullbody"
      asset_type: "character_reference"
      source_script_selectors: ["scene01_cut01"]
      story_purpose: "舞踏会前後で同一人物として見えるための基準参照"
      semantic_contract:
        must_match_story_role: "灰かぶりから舞踏会へ向かう主人公"
        must_not_include: ["ガラスの靴を常時手に持つ"]
        must_appear_in_selectors: "scene01_cut01"
        must_not_appear_in_selectors:
          - "scene03_cut02"
        allowed_contexts:
          - "作業着の全身参照"
      visual_spec:
        identity: ["若い女性", "灰をかぶった作業着"]
      generation_plan:
        output: "assets/characters/cinderella_fullbody.png"
        required_views: ["front", "side", "back"]
        execution_lane: "bootstrap_builtin"
        reference_inputs: []
      existing_outputs: ["assets/characters/cinderella_fullbody.png"]
      review:
        status: "approved"
  objects:
    - asset_id: "glass_slipper"
      aliases: ["slipper", "crystal_shoe"]
      asset_type: "object_reference"
      source_script_selectors: ["scene03_cut02"]
      story_purpose: "王子が探す物語固有アイテム"
      semantic_contract:
        must_appear_in_selectors:
          - "scene03_cut02"
        must_not_appear_in_selectors: "scene01_cut01"
        allowed_contexts: "王子が手がかりとして確認する場面"
      visual_spec:
        identity: ["透明なガラスの靴"]
      generation_plan:
        output: "assets/objects/glass_slipper.png"
        execution_lane: "bootstrap_builtin"
        reference_inputs: []
      review:
        status: "approved"
  locations: []
  setpieces: []
  reusable_stills: []
```
""",
        encoding="utf-8",
    )
    (run_dir / "asset_generation_requests.md").write_text(
        """# Asset Generation Requests

## cinderella_fullbody

- tool: `codex_builtin_image`
- asset_id: `cinderella_fullbody`
- asset_type: `character_reference`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- review_status: `approved`
- output: `assets/characters/cinderella_fullbody.png`

```text
シンデレラ全身参照。
```

## glass_slipper

- tool: `codex_builtin_image`
- asset_id: `glass_slipper`
- asset_type: `object_reference`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- review_status: `approved`
- output: `assets/objects/glass_slipper.png`

```text
透明なガラスの靴。
```
""",
        encoding="utf-8",
    )
    (run_dir / "asset_generation_manifest.md").write_text(
        """```yaml
asset_generation_manifest:
  items:
    - asset_id: "cinderella_fullbody"
      asset_type: "character_reference"
      status: "created"
      output: "assets/characters/cinderella_fullbody.png"
    - asset_id: "glass_slipper"
      asset_type: "object_reference"
      status: "requested"
      output: "assets/objects/glass_slipper.png"
```
""",
        encoding="utf-8",
    )
    (run_dir / "video_manifest.md").write_text(
        """```yaml
scenes:
  - scene_id: "scene01"
    cuts:
      - selector: "scene01_cut01"
        image_generation:
          character_ids: ["cinderella_fullbody", "glass_slipper"]
          object_ids: []
          references: ["assets/characters/cinderella_fullbody.png"]
      - selector: "scene03_cut02"
        image_generation:
          character_ids: []
          object_ids: ["glass_slipper"]
          references:
            - asset_id: "glass_slipper"
      - selector: "scene04_cut01"
        image_generation:
          character_ids: []
          object_ids: ["pumpkin_carriage"]
          references: []
```
""",
        encoding="utf-8",
    )
    (run_dir / "assets" / "characters").mkdir(parents=True)
    (run_dir / "assets" / "characters" / "cinderella_fullbody.png").write_bytes(b"fake png")
    (run_dir / "logs" / "review" / "semantic").mkdir(parents=True)
    (run_dir / "logs" / "review" / "semantic" / "asset_output.contact_sheet.png").write_bytes(b"sheet")


class TestSemanticPackAsset(unittest.TestCase):
    def test_collect_asset_plan_entries_include_contracts_and_usage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_asset_") as td:
            run_dir = Path(td)
            _write_asset_fixture(run_dir)

            entries = collect_entries("asset_plan", run_dir)

            self.assertEqual([entry["asset_id"] for entry in entries], ["cinderella_fullbody", "glass_slipper", "pumpkin_carriage"])
            cinderella = entries[0]
            self.assertEqual(cinderella["category"], "characters")
            self.assertEqual(cinderella["asset_type"], "character_reference")
            self.assertEqual(cinderella["source_paths"], ["asset_inventory.md", "asset_plan.md", "video_manifest.md"])
            self.assertEqual(cinderella["used_by_selectors"], ["scene01_cut01"])
            self.assertEqual(cinderella["semantic_contract"]["must_match_story_role"], "灰かぶりから舞踏会へ向かう主人公")
            self.assertEqual(cinderella["canonical_asset_id"], "cinderella_fullbody")
            self.assertIn("assets/characters/cinderella_fullbody.png", cinderella["aliases"])
            self.assertIn("cinderella_fullbody", cinderella["aliases"])
            self.assertEqual(cinderella["semantic_contract"]["must_appear_in_selectors"], ["scene01_cut01"])
            self.assertEqual(cinderella["semantic_contract"]["must_not_appear_in_selectors"], ["scene03_cut02"])
            self.assertEqual(cinderella["semantic_contract"]["allowed_contexts"], ["作業着の全身参照"])
            self.assertIn("forbidden props or later-story objects are not accidentally attached", cinderella["review_rubric"])
            self.assertFalse(cinderella["planned_but_unused"])
            self.assertFalse(cinderella["used_but_unplanned"])
            self.assertEqual(cinderella["wrong_category_usage"], [])
            self.assertEqual(cinderella["suggested_fix_targets"], ["asset_plan.md", "image_generation_requests.md"])

            slipper = entries[1]
            self.assertEqual(slipper["canonical_asset_id"], "glass_slipper")
            self.assertIn("slipper", slipper["aliases"])
            self.assertEqual(slipper["semantic_contract"]["must_not_appear_in_selectors"], ["scene01_cut01"])
            self.assertIn("object material, scale, and uniqueness match the story-specific function", slipper["review_rubric"])
            self.assertEqual(slipper["used_by_selectors"], ["scene01_cut01", "scene03_cut02"])
            self.assertEqual(slipper["wrong_category_usage"][0]["usage_key"], "character_ids")
            self.assertEqual(slipper["suggested_fix_targets"], ["asset_plan.md", "video_manifest.md", "image_generation_requests.md"])

            unplanned = entries[2]
            self.assertEqual(unplanned["asset_id"], "pumpkin_carriage")
            self.assertEqual(unplanned["canonical_asset_id"], "pumpkin_carriage")
            self.assertTrue(unplanned["used_but_unplanned"])
            self.assertEqual(unplanned["used_by_selectors"], ["scene04_cut01"])
            self.assertEqual(unplanned["suggested_fix_targets"], ["asset_inventory.md", "asset_plan.md", "video_manifest.md"])

    def test_collect_asset_output_entries_include_outputs_requests_and_contact_sheets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_asset_") as td:
            run_dir = Path(td)
            _write_asset_fixture(run_dir)

            entries = collect_entries("asset_output", run_dir)
            by_id = {entry["asset_id"]: entry for entry in entries}

            self.assertEqual(by_id["cinderella_fullbody"]["stage"], "asset_output")
            self.assertTrue(by_id["cinderella_fullbody"]["generated_outputs"][0]["exists"])
            self.assertFalse(by_id["glass_slipper"]["generated_outputs"][0]["exists"])
            self.assertEqual(by_id["glass_slipper"]["request_metadata"]["asset_type"], "object_reference")
            self.assertEqual(by_id["glass_slipper"]["generation_manifest_item"]["status"], "requested")
            self.assertEqual(by_id["cinderella_fullbody"]["contact_sheets"], ["logs/review/semantic/asset_output.contact_sheet.png"])
            self.assertIn("asset_generation_requests.md", by_id["cinderella_fullbody"]["source_paths"])
            self.assertTrue(by_id["pumpkin_carriage"]["used_but_unplanned"])

    def test_inventory_only_plan_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_asset_") as td:
            run_dir = Path(td)
            (run_dir / "asset_inventory.md").write_text(
                """```yaml
asset_inventory:
  items:
    - item_id: "ballroom"
      category: "location"
      source_script_selectors: ["scene02"]
      story_purpose: "舞踏会の主要ロケーション"
      reusable_reason: "複数 cut の空間連続性"
      recommended_asset_type: "location_reference"
```""",
                encoding="utf-8",
            )

            entries = collect_entries("asset_plan", run_dir)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["asset_id"], "ballroom")
            self.assertEqual(entries[0]["canonical_asset_id"], "ballroom")
            self.assertIn("space, era, geography, and mood match the scene context", entries[0]["review_rubric"])
            self.assertEqual(entries[0]["semantic_contract"]["must_appear_in_selectors"], [])
            self.assertTrue(entries[0]["inventory_only"])

    def test_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_asset_") as td:
            with self.assertRaises(ValueError):
                collect_entries("scene_set", Path(td))


if __name__ == "__main__":
    unittest.main()
