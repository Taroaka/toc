"""Image-only readiness, independent of later narration text and audio bytes."""
import copy

from toc.run_root_binding import read_run_file_bytes
from toc.visual_planning_contract import decode_document

POLICY = 'scene_image_consistency_v1'
BASE = 'logs/image_consistency'


def visual_inputs(value):
    """Omit audio-owned fields; never truncate image or story instructions."""
    if isinstance(value, list):
        return [visual_inputs(item) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    excluded = {'audio', 'audio_story_plan', 'tts_text', 'elevenlabs',
                'elevenlabs_prompt', 'native_audio', 'human_review'}
    return {key: visual_inputs(item) for key, item in value.items()
            if key not in excluded and not key.startswith('narration')}


def image_snapshot(root, data, scene_id):
    from toc import scene_direction_service as service
    visual = visual_inputs(data)
    snapshot = service.scene_snapshot(root, visual, scene_id)
    binding_files = dict(snapshot['files'])
    # Raw bytes remain in snapshot.files for the transaction/publication check.
    # The reusable readiness identity excludes narration-only script edits.
    if binding_files.get('script.md') is not None:
        binding_files['script.md'] = service.digest(visual_inputs(
            decode_document(read_run_file_bytes(root, 'script.md'))))
    snapshot['digest'] = service.digest({
        'policy': POLICY, 'scene': service.scene_binding(snapshot['scene']),
        'resources': visual.get('resources', visual.get('assets')),
        'film': {k: v for k, v in (visual.get('video_metadata') or {}).items()
                 if k not in ('duration_seconds', 'video_preparation')},
        'boundaries': snapshot['boundaries'], 'files': binding_files,
    })
    return snapshot
