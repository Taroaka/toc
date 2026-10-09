"""Read-only full-run scope checks. Set TOC_NARRATION_TEST_RUN_DIR to a run.

Uses unittest and the prompt builder directly; no harness, provider or writeback.
The run is an explicit input, so these checks work for any story.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import unittest

import yaml


class TestNarrationFullRunScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get('TOC_NARRATION_TEST_RUN_DIR')
        if not value:
            raise unittest.SkipTest('Set TOC_NARRATION_TEST_RUN_DIR to the run to inspect')
        cls.run_dir = Path(value).resolve(strict=True)
        cls.sources = {name: hashlib.sha256((cls.run_dir / name).read_bytes()).hexdigest()
                       for name in ('research.md', 'story.md', 'script.md', 'video_manifest.md')}
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('full_run_narration_scope', root / 'scripts/ai/toc-immersive-narration-multiagent.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.data = yaml.safe_load(cls.module.extract_yaml_block((cls.run_dir / 'video_manifest.md').read_text()))
        cls.scenes = [scene for scene in cls.data['scenes']
                      if not cls.module.is_non_renderable_manifest_node(scene)]
        cls.scene_ids = [cls.module._normalized_id(scene['scene_id']) for scene in cls.scenes]
        cls.inventory = [(cls.module.make_scene_cut_selector(scene['scene_id'], cut['cut_id']), cut)
                         for scene in cls.scenes for cut in scene.get('cuts', [])
                         if not cls.module.is_non_renderable_manifest_node(cut)]
        if not cls.inventory:
            raise AssertionError('Selected run has no active cuts')
        print(f'Full-run scope: {cls.run_dir.name}; {len(cls.scenes)} scenes, {len(cls.inventory)} cuts; '
              f'statuses={dict(Counter(cls.module._authoring_status(cls.module._cut_audio_narration(c)) for _, c in cls.inventory))}')

    @classmethod
    def tearDownClass(cls):
        for name, before in cls.sources.items():
            if hashlib.sha256((cls.run_dir / name).read_bytes()).hexdigest() != before:
                raise AssertionError(f'Production source changed: {name}')

    def test_prompt_covers_every_active_cut_once_in_canonical_order(self):
        before = deepcopy(self.data)
        prompt = self.module._prompt_text(self.data, self.scene_ids)
        actual = re.findall(r'^- `(scene[^`]+)`$', prompt, re.MULTILINE)
        expected = [selector for selector, _ in self.inventory]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(self.data, before)
        for rule in ('音声だけで理解できる説明の具体性', 'どこから／どこへ、いつまでに、なぜ',
                     '尺が足りない場合は意味に必要な語を削らず', '原作にない動機・帰宅条件・例外を創作せず'):
            self.assertIn(rule, prompt)

    def test_every_cut_preserves_current_text_and_protection_in_scratch_seed(self):
        for selector, cut in self.inventory:
            with self.subTest(cut=selector):
                before = deepcopy(cut)
                narration = self.module._cut_audio_narration(cut)
                seed = self.module._scene_cut_scratch(str(cut['cut_id']), cut)
                status = self.module._authoring_status(narration)
                text = str(narration.get('text') or '').strip()
                self.assertEqual(seed['narration_text'], text)
                self.assertEqual(seed['tts_text'], str(narration.get('tts_text') or text).strip())
                self.assertEqual(seed['read_only'], status in {'human_locked', 'reviewed', 'silent'})
                self.assertEqual(seed['locked'], seed['read_only'])
                self.assertEqual(cut, before)

    def test_full_run_locked_inventory_has_no_missing_or_extra_cuts(self):
        expected = [selector for selector, cut in self.inventory
                    if self.module._authoring_status(self.module._cut_audio_narration(cut))
                    in {'human_locked', 'reviewed', 'silent'}]
        locked = self.module._locked_cut_inventory(self.scenes, self.scene_ids)
        self.assertEqual([item['selector'] for item in locked], expected)
        self.assertTrue(all(item['read_only'] for item in locked))


if __name__ == '__main__':
    unittest.main()
