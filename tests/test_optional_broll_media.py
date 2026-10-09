from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml

from toc.story_duration import measure_manifest_runtime

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def broll_cut():
    return {
        'cut_id': 1,
        'image_generation': {'api_prompt_payload': {'shot_design_contract': {'a_roll_or_b_roll': 'b_roll'}}},
        'video_generation': {'tool': 'kling_3_0', 'duration_seconds': 4, 'output': 'assets/scenes/scene1_cut1.mp4'},
    }


class OptionalBrollTests(unittest.TestCase):
    def test_broll_audio_omission_passes_asset_guard(self):
        mod = load_script('generate-assets-from-manifest')
        _, _, scenes = mod.parse_manifest_yaml_full(yaml.safe_dump({'scenes': [{'scene_id': 1, 'cuts': [broll_cut()]}]}))
        mod.validate_scene_narration(scenes=scenes, require=True, scene_filter=None)
        self.assertFalse(scenes[0].narration_output)

    def test_broll_duration_does_not_need_audio_file(self):
        measurement = measure_manifest_runtime({'scenes': [{'scene_id': 1, 'cuts': [broll_cut()]}]}, base_dir=Path('/virtual/run'), probe=lambda _: self.fail('B-roll must not probe absent audio'))
        self.assertTrue(measurement.complete, measurement)
        self.assertEqual(measurement.intentional_silence_seconds, 4)
        self.assertEqual(measurement.effective_seconds, 4)

    def test_explicit_broll_audio_still_requires_output(self):
        cut = broll_cut()
        cut['audio'] = {'narration': {'tool': 'elevenlabs', 'text': '明示した音声'}}
        mod = load_script('generate-assets-from-manifest')
        _, _, scenes = mod.parse_manifest_yaml_full(yaml.safe_dump({'scenes': [{'scene_id': 1, 'cuts': [cut]}]}))
        with self.assertRaisesRegex(SystemExit, 'missing audio.narration.output'):
            mod.validate_scene_narration(scenes=scenes, require=True, scene_filter=None)

    def test_non_broll_audio_omission_remains_invalid(self):
        cut = broll_cut()
        cut['image_generation']['api_prompt_payload']['shot_design_contract']['a_roll_or_b_roll'] = 'a_roll'
        measurement = measure_manifest_runtime({'scenes': [{'scene_id': 1, 'cuts': [cut]}]}, base_dir=Path('/virtual/run'), probe=lambda _: None)
        self.assertFalse(measurement.complete)
        self.assertIn('scene1_cut1:narration', measurement.missing_items)

    def test_sync_omitted_broll_narration_without_inventing_human_confirmation(self):
        cut = broll_cut()
        script_cut = {'cut_id': 1, 'narration': '', 'tts_text': ''}
        load_script('sync-narration-from-script')._sync_human_fields_to_manifest_cut(cut, script_cut, selector='scene1_cut1')
        narration = cut['audio']['narration']
        self.assertEqual(narration['tool'], 'silent')
        self.assertEqual(narration['authoring_status'], 'silent')
        self.assertEqual(narration['silence_contract']['kind'], 'b_roll')
        self.assertNotEqual(narration['silence_contract'].get('confirmed_by_human'), True)

    def test_frontend_recognizes_audio_free_broll(self):
        from server.image_gen_app import _narration_audio_readiness, _manifest_narration_items
        data = {'scenes': [{'scene_id': 1, 'cuts': [broll_cut()]}]}
        self.assertTrue(_narration_audio_readiness(Path('/virtual/run'), data)['ready'])
        item = _manifest_narration_items(Path('/virtual/run'), data)[0]
        self.assertEqual(item['narrationTool'], 'silent')
        self.assertIsNone(item['narrationOutput'])

class BrollBoundaryTests(unittest.TestCase):
    def test_empty_output_with_explicit_silent_broll_is_optional(self):
        from toc.script_narration import resolve_manifest_narration
        cut = broll_cut()
        cut["audio"] = {"narration": {"tool": "silent", "text": "", "output": None}}
        self.assertEqual(resolve_manifest_narration(cut)["silence_contract"]["kind"], "b_roll")

    def test_script_sync_is_idempotent_and_preserves_subtitles(self):
        cut = broll_cut()
        cut["text_overlay"] = {"main_text": "字幕のみ"}
        source = {"cut_id": 1, "narration": "", "tts_text": "", "cut_contract": {"a_roll_or_b_roll": "b_roll"}}
        sync = load_script("sync-narration-from-script")
        sync._sync_human_fields_to_manifest_cut(cut, source, selector="scene1_cut1")
        before = deepcopy(cut)
        sync._sync_human_fields_to_manifest_cut(cut, source, selector="scene1_cut1")
        self.assertEqual(cut, before)
        self.assertEqual(cut["text_overlay"]["main_text"], "字幕のみ")

    def test_optional_broll_can_later_receive_authored_speech(self):
        cut = broll_cut()
        source = {"cut_id": 1, "narration": "", "tts_text": ""}
        sync = load_script("sync-narration-from-script")
        sync._sync_human_fields_to_manifest_cut(cut, source, selector="scene1_cut1")
        source.update(narration="追加した声", tts_text="ついかしたこえ")
        sync._sync_human_fields_to_manifest_cut(cut, source, selector="scene1_cut1")
        self.assertEqual(cut["audio"]["narration"]["tool"], "elevenlabs")
        self.assertEqual(cut["audio"]["narration"]["text"], "追加した声")

    def test_resolver_preserves_explicit_audio_and_subtitles(self):
        from toc.script_narration import resolve_manifest_narration
        for narration in (
            {'tool': 'elevenlabs', 'text': '音声', 'output': 'assets/audio/voice.mp3'},
            {'tool': 'elevenlabs'},
            {'output': 'assets/audio/existing.mp3'},
            {'revision': {'schema_version': 'narration_revision_v1'}},
        ):
            with self.subTest(narration=narration):
                cut = broll_cut()
                cut['audio'] = {'narration': narration, 'bgm': {'output': 'music.mp3'}}
                cut['text_overlay'] = {'main_text': '任意の字幕'}
                before = deepcopy(cut)
                self.assertIs(resolve_manifest_narration(cut), narration)
                self.assertEqual(cut, before)

    def test_resolver_rejects_malformed_audio(self):
        from toc.script_narration import resolve_manifest_narration
        for audio in ('broken', [], {'narration': 'broken'}, {'narration': []}, {'narration': {'tool': []}}):
            cut = broll_cut()
            cut['audio'] = audio
            result = resolve_manifest_narration(cut)
            self.assertNotEqual((result or {}).get('tool'), 'silent')

    def test_canonical_a_roll_overrides_derived_b_roll(self):
        from toc.script_narration import is_b_roll, resolve_manifest_narration
        cut = broll_cut()
        cut['cut_contract'] = {'a_roll_or_b_roll': 'a_roll'}
        self.assertFalse(is_b_roll(cut))
        self.assertIsNone(resolve_manifest_narration(cut))

    def test_canonical_broll_works_without_image_projection(self):
        cut = broll_cut()
        cut.pop('image_generation')
        cut['cut_contract'] = {'a_roll_or_b_roll': 'b_roll'}
        measurement = measure_manifest_runtime({'scenes': [{'scene_id': 1, 'cuts': [cut]}]}, base_dir=Path('/virtual/run'), probe=lambda _: None)
        self.assertTrue(measurement.complete)

    def test_missing_broll_duration_still_fails(self):
        cut = broll_cut()
        cut['video_generation'].pop('duration_seconds')
        measurement = measure_manifest_runtime({'scenes': [{'scene_id': 1, 'cuts': [cut]}]}, base_dir=Path('/virtual/run'), probe=lambda _: None)
        self.assertFalse(measurement.complete)
        self.assertIn('scene1_cut1:silence_duration', measurement.missing_items)

    def test_mixed_audio_timeline_keeps_broll_gap(self):
        spoken = {'cut_id': 2, 'video_generation': {'duration_seconds': 6}, 'audio': {'narration': {'tool': 'elevenlabs', 'output': 'spoken.mp3'}}}
        measurement = measure_manifest_runtime({'scenes': [{'scene_id': 1, 'cuts': [broll_cut(), spoken]}]}, base_dir=Path('/virtual/run'), probe=lambda _: 6)
        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.audio_timeline_seconds, 10)
        self.assertEqual(measurement.effective_seconds, 10)

    def test_duration_sync_accepts_broll_without_audio(self):
        mod = load_script('sync-manifest-durations-from-audio')
        self.assertTrue(mod._is_intentional_silent(broll_cut()))
        self.assertTrue(mod._has_complete_silence_contract(broll_cut()))

    def test_silent_broll_verification_needs_no_audio_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            manifest = {'scenes': [{'scene_id': 1, 'cuts': [broll_cut()]}]}
            (run_dir / 'video_manifest.md').write_text('```yaml\n' + yaml.safe_dump(manifest) + '```\n')
            result, _ = load_script('verify-pipeline').check_narration(run_dir)
            self.assertTrue(result['passed'], result)

    def test_clip_list_padding_preserves_timing_without_changing_manifest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'video_manifest.md'
            spoken = {'cut_id': 2, 'video_generation': {'output': 'second.mp4'}, 'audio': {'narration': {'output': 'second.mp3'}}}
            original = '```yaml\n' + yaml.safe_dump({'scenes': [{'scene_id': 1, 'cuts': [broll_cut(), spoken]}]}) + '```\n'
            path.write_text(original)
            clips, audios, _ = load_script('build-clip-lists').parse_manifest(path, materialize_silence=True)
            self.assertEqual(len(clips), 2)
            self.assertEqual(len(audios), 2)
            self.assertIn('render_padding/b_roll_', audios[0])
            self.assertTrue((path.parent / audios[0]).is_file())
            self.assertEqual(audios[1], 'second.mp3')
            self.assertEqual(path.read_text(), original)

class BrollAuthoringTests(unittest.TestCase):
    def test_all_broll_can_prepare_and_merge_without_spoken_story(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            cut = broll_cut()
            manifest = {'scenes': [{'scene_id': 10, 'cuts': [cut]}]}
            script = {'scenes': [{'scene_id': 10, 'cuts': [{'cut_id': 1, 'narration': '', 'tts_text': ''}]}]}
            (run_dir / 'video_manifest.md').write_text('```yaml\n' + yaml.safe_dump(manifest) + '```\n')
            (run_dir / 'script.md').write_text('```yaml\n' + yaml.safe_dump(script) + '```\n')
            for command in ('toc-immersive-narration-multiagent', 'merge-immersive-narration'):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'ai' / f'{command}.py'), '--run-dir', str(run_dir)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = yaml.safe_load((run_dir / 'video_manifest.md').read_text().split('```yaml\n')[1].split('```')[0])
            narration = result['scenes'][0]['cuts'][0]['audio']['narration']
            self.assertEqual(narration['tool'], 'silent')
            self.assertFalse(narration.get('output'))


if __name__ == '__main__':
    unittest.main()
