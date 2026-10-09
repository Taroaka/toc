import array
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from server import image_gen_app as app


class TestNarrationLeadIn(unittest.TestCase):
    def test_video_minimum_includes_lead_in(self):
        run = Path('/tmp/narration_lead_in_fixture')
        node = {'audio': {'narration': {'output': 'audio.mp3'}}, 'render': {'narration_offset_seconds': 0.5}}
        with patch.object(app, '_read_manifest_data', return_value=(run/'video_manifest.md', '', {})), patch.object(app, '_target_by_item_id', return_value={'cut':node}), patch.object(app, 'current_audio_candidate', return_value=None), patch.object(app, '_validate_run_relative_audio_path'), patch.object(app, '_probe_media_duration_seconds', return_value=4.8):
            self.assertAlmostEqual(app._narration_min_duration_seconds(run, 'scene1_cut1'), 5.3)

    def test_duration_sync_rounds_up_audio_plus_lead_in(self):
        run = Path('/tmp/narration_lead_in_fixture')
        node = {'video_generation': {'duration_seconds':5}, 'render': {'narration_offset_seconds':0.5}}
        with patch.object(app, '_read_manifest_data', return_value=(run/'video_manifest.md', '', {})), patch.object(app, '_target_by_item_id', return_value={'cut':node}), patch.object(app, '_write_manifest_data'), patch.object(app, '_backup_run_file'):
            app._apply_audio_duration_to_manifest(run, {'scene1_cut1':4.8})
        self.assertEqual(node['video_generation']['duration_seconds'], 6)
        self.assertEqual(node['render']['narration_offset_seconds'], 0.5)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg required')
    def test_render_inserts_silence_without_losing_spoken_audio(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            source = run/'tone.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1.2','-ar','44100',str(source)],check=True,capture_output=True)
            item=app.RenderInputItem(item_id='scene1_cut1',video_path='unused.mp4',video_duration_seconds=3,narration_path='tone.wav',narration_offset_seconds=0.5)
            output=app._prepare_render_narration(run, source, item, strict=True)
            pcm=subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','f32le','-ac','1','-ar','44100','-'],check=True,capture_output=True).stdout
            samples=array.array('f');samples.frombytes(pcm)
            def energy(start,end):
                values=samples[int(start*44100):int(end*44100)]
                return sum(x*x for x in values)/len(values)
            self.assertLess(energy(0.05,0.35),1e-5)
            self.assertGreater(energy(0.65,0.95),1e-4)
            self.assertGreater(energy(1.35,1.55),1e-4)
            self.assertLess(energy(2.3,2.7),1e-5)


if __name__=='__main__':unittest.main()
