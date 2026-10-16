"""Recover parent video containers corrupted by the pre-shot materializer.

Reproject only from current canonical direction/story; never relax timelines.
Use --apply after inspecting the dry-run report. Existing run lock is retained.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.world_walk_source import (directory_identity_nofollow, ensure_directory_relative_nofollow,
    read_regular_file_nofollow, write_regular_file_nofollow, open_directory_nofollow)
from toc.runtime_locks import sync_file_lock
from toc.p400_authoring import load_direction, projection_issues
from toc.p400_projection import project_scene
from toc.source_scene_projection import source_scene_event
from toc.visual_planning_contract import decode_document, story_scenes
from toc.shot_timeline import validate_projected_shot_schedule
import yaml

args = argparse.ArgumentParser()
args.add_argument('run_dir', type=Path)
args.add_argument('--apply', action='store_true')
opt = args.parse_args()
r = opt.run_dir.resolve()
identity = directory_identity_nofollow(r)
sha = lambda raw: hashlib.sha256(raw).hexdigest()
descriptor = open_directory_nofollow(r, expected_identity=identity)
with sync_file_lock(r/'.locks/create_resume.lock', wait=False, run_root_descriptor=descriptor, expected_run_root_identity=identity):
    original = read_regular_file_nofollow(r, 'video_manifest.md')
    data = decode_document(original)
    story = decode_document(read_regular_file_nofollow(r, 'story.md'))
    direction = load_direction(r)
    candidate = deepcopy(data)
    receipt = {'before_sha256': sha(original), 'direction_sha256': sha(read_regular_file_nofollow(r, 'cinematic_direction.json')),
               'story_sha256': sha(read_regular_file_nofollow(r, 'story.md')), 'parents': []}
    assert len(candidate['scenes']) == len(direction['scenes']) == len(story_scenes(story))
    for i, (row, planned, source) in enumerate(zip(candidate['scenes'], direction['scenes'], story_scenes(story))):
        assert row['cinematic_direction'] == planned
        location = source.get('location') or {}
        name = location.get('name', '') if isinstance(location, dict) else str(location)
        event = source_scene_event(source, runtime_scene_id=row['scene_id'], location_name=name)
        rows = candidate['scenes']
        projected = project_scene(planned, source_scene=source, scene_id=row['scene_id'], resources=direction['resources'],
            scene_intent=row.get('scene_intent', {}), scene_event=event, scene_generation={}, acceptance_draft={},
            acceptance_binding={}, previous_selector=(f"scene{rows[i-1]['scene_id']}_cut{len(direction['scenes'][i-1]['cuts']):02d}" if i else ''),
            next_selector=(f"scene{rows[i+1]['scene_id']}_cut01" if i+1 < len(rows) else ''),
            story_time=data['video_metadata'].get('time', ''), film_language=direction.get('film_language'),
            cast_design=direction.get('cast_design'), available_state_variants=[v for sc in direction['scenes'] for v in sc.get('state_variants', [])])
        assert len(row['cuts']) == len(projected[1]['cuts'])
        for cut, expected in zip(row['cuts'], projected[1]['cuts']):
            if not cut.get('shots'):
                continue
            assert 'shot_direction_override' not in cut
            assert cut['shot_plan'] == expected['shot_plan']
            assert cut['duration_seconds'] == expected['duration_seconds']
            assert cut['authored_cut_id'] == expected['authored_cut_id']
            before, after = cut['video_generation'], expected['video_generation']
            if before == after:
                continue
            # Known corruption signature: the final child's provider request was
            # stored into the parent while all child timelines remained intact.
            last = cut['shots'][-1]
            assert before['output'] == last['video_generation']['output']
            assert before['first_frame'] == last['video_generation']['first_frame']
            assert before['duration_seconds'] == last['video_generation']['duration_seconds']
            receipt['parents'].append({'selector': cut['selector'], 'before': before, 'after': after})
            cut['video_generation'] = deepcopy(after)
    issues = projection_issues(candidate, 'video_metadata', direction, story)
    assert not issues, issues[:10]
    for row in candidate['scenes']:
        for cut in row['cuts']:
            validate_projected_shot_schedule(cut, parent_selector=cut['selector'])
    print(json.dumps({'affected_parents': len(receipt['parents']), 'projection_issues': issues,
                      'before_sha256': receipt['before_sha256']}, ensure_ascii=False))
    if opt.apply and receipt['parents']:
        # Persist a reversible before-image and exact field receipt under lease.
        rel = 'logs/repairs/parent-video-projection'
        ensure_directory_relative_nofollow(r, rel)
        for name, raw in [('before.md', original), ('receipt.json', json.dumps(receipt, ensure_ascii=False, indent=2).encode())]:
            write_regular_file_nofollow(destination_root=r, destination_relative=f'{rel}/{name}', data=raw,
                expected_destination_root_identity=identity, exclusive=True)
        assert sha(read_regular_file_nofollow(r, 'video_manifest.md')) == sha(original)
        raw = ('# Video Manifest\n\n```yaml\n' + yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False) + '```\n').encode()
        write_regular_file_nofollow(destination_root=r, destination_relative='video_manifest.md', data=raw,
            expected_destination_root_identity=identity)
        print('Restored source-projected parent video containers; shots unchanged.')
