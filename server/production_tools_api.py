"""Optional, local production tools. Media generation and source authoring stay separate."""
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Literal

try:
    from fastapi import HTTPException
except ModuleNotFoundError:  # The existing canonical CLI can run without the web app.
    class HTTPException(RuntimeError):
        pass
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, ImageOps

from scripts.world_walk_source import read_regular_file_nofollow
from toc import asset_variants, candidate_notes, sound_design
from toc.spatial_previs import validate_geometry, project_geometry

PREFIX = '/api/image-gen/production-tools'
SELECTIONS = 'production_selections.json'
SPATIAL = 'spatial_previews.json'


def app():
    from server import image_gen_app
    return image_gen_app


class TargetRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')


class NoteRequest(TargetRequest):
    kind: Literal['image', 'video']
    candidate_path: str = Field(max_length=500)
    candidate_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: int = Field(ge=0)
    disposition: Literal['keep', 'reject', 'undecided'] = 'undecided'
    problem: str = Field(default='', max_length=4000)
    change: str = Field(default='', max_length=4000)
    result: str = Field(default='', max_length=4000)


class VariantRequest(TargetRequest):
    base_path: str = Field(max_length=500)
    edited_path: str = Field(max_length=500)
    base_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    edited_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    regions: list[dict[str, float]] = Field(min_length=1, max_length=32)
    state_description: str = Field(min_length=1, max_length=2000)


class EditRequest(TargetRequest):
    source_path: str = Field(max_length=500)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    settings: dict[str, Any]


class SelectRequest(TargetRequest):
    path: str = Field(max_length=500)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class GeometryRequest(TargetRequest):
    kind: Literal['image', 'video']
    geometry: dict[str, Any]
    expected_revision: int = Field(ge=0)


def _load(root, name, default):
    try:
        value = json.loads(read_regular_file_nofollow(root, name))
    except FileNotFoundError:
        return default
    if not isinstance(value, dict) or value.get('schema_version') != default['schema_version']:
        raise ValueError(f'invalid {name}')
    return value


def _sha(root: Path, path: str) -> str:
    return hashlib.sha256(read_regular_file_nofollow(root, path)).hexdigest()


def _target(root, item_id, kind, data=None):
    api = app()
    if data is None:
        try:
            _, _, data = api._read_manifest_data(root)
        except FileNotFoundError:
            if kind != 'image':
                raise
            data = {}
    target = (api._video_target_by_item_id(data, item_id) if kind == 'video'
              else api._target_by_item_id(data, item_id))
    request = None
    if kind == 'image':
        for group in ('asset', 'scene'):
            try:
                request = next((r for r in api.load_request_items(root, group) if r.id == item_id), None)
            except FileNotFoundError:
                continue
            if request:
                break
    if target is None and request is None:
        raise ValueError('対象の素材またはカットが見つかりません')
    return data, target, request


def _video_revision(root, item_id, data):
    api = app()
    current = api._current_video_candidate_provenance(root, item_id, manifest_data=data)
    if current:
        return current['revision_id']
    target = api._video_target_by_item_id(data, item_id)
    node = target['cut'] if target else {}
    generation = node.get('video_generation', {})
    source = {'cut_contract': node.get('cut_contract'),
              'generation': {k: v for k, v in generation.items() if k not in {'output', 'selected_candidate'}}}
    return 'legacy:' + api.sha256_canonical_json(source)


def selected_video_path(root, item_id, data=None):
    document = _load(root, SELECTIONS, {'schema_version': 'production_selections_v1', 'items': {}})
    record = document.get('items', {}).get(item_id)
    if record is None:
        return None
    if data is None:
        _, _, data = app()._read_manifest_data(root)
    if record.get('request_revision') != _video_revision(root, item_id, data):
        raise ValueError('selected video request is stale; select a current candidate')
    if _sha(root, record['path']) != record.get('sha256'):
        raise ValueError('selected video bytes changed; select a current candidate')
    if record.get('receipt_path'):
        from toc.video_editing import verify_video_edit
        if _sha(root, record['receipt_path']) != record.get('receipt_sha256'):
            raise ValueError('selected video edit receipt changed')
        verify_video_edit(root, record['path'], request_revision=record['request_revision'])
    return record['path']


def _media(root, path, kind, label):
    api = app()
    if not path:
        return None
    validate = api._validate_run_relative_image_path if kind == 'image' else api._validate_run_relative_video_path
    validate(root, path, must_exist=False)
    absolute = root / path
    if not absolute.is_file():
        return None
    result = {'path': path, 'sha256': _sha(root, path), 'label': label}
    if kind == 'image':
        with Image.open(absolute) as image:
            oriented = ImageOps.exif_transpose(image)
            result.update(width=oriented.width, height=oriented.height)
    else:
        result['duration_seconds'] = api._probe_media_duration_seconds(absolute)
    return result


def _assets(node, request, data):
    result = {}
    contract = node.get('cut_contract', {})
    dependency = contract.get('asset_dependency', {})
    ids = set(dependency.get('character_ids_required', []) + dependency.get('object_ids_required', [])
              + dependency.get('location_ids_required', [])
              + node.get('image_generation', {}).get('character_ids', []) + node.get('image_generation', {}).get('object_ids', []))
    bibles = data.get('assets', {})
    for key, id_key in [('character_bible', 'character_id'), ('object_bible', 'object_id'), ('location_bible', 'location_id')]:
        for asset in bibles.get(key, []) if isinstance(bibles.get(key), list) else []:
            asset_id = asset.get(id_key) or asset.get('asset_id')
            if asset_id in ids or (request and asset_id == request.id):
                result[asset_id] = asset.get('name') or asset.get('display_name') or asset_id
    for asset_id in ids:
        result.setdefault(asset_id, asset_id)
    return result


def context(root: Path, item_id: str, kind: str):
    api = app()
    data, target, request = _target(root, item_id, kind)
    node = target['cut'] if target else {}
    generation = node.get('video_generation', {})
    image_generation = node.get('image_generation', {})
    paths = {}
    revisions_by_path = {}
    references = {}
    variants = asset_variants.list_variants(root, item_id)
    edits = []
    if kind == 'image':
        current = (request.existing_image or request.output) if request else image_generation.get('output')
        if current:
            paths[current] = '現在の画像'
        for row in api.list_candidate_items(root, item_id):
            paths[row['path']] = f"候補 {row['index']}"
        for record in variants:
            if not record['stale']:
                paths[record['path']] = record['state_description']
        for path in (request.references if request else image_generation.get('references', [])):
            references[path] = Path(path).name
        references.update(paths)
        request_revision = str(image_generation.get('api_prompt_payload', {}).get('source_digest') or '')
    else:
        from toc.video_editing import list_video_edits
        request_revision = _video_revision(root, item_id, data)
        if generation.get('output'):
            paths[generation['output']] = '現在の動画'
        base = root / 'assets/test/video_gen_candidates' / api._safe_artifact_id(item_id)
        if base.is_dir() and not base.is_symlink():
            for path in sorted(base.glob('*/*.mp4'))[:128]:
                if not path.name.startswith('.'):
                    paths[path.relative_to(root).as_posix()] = path.stem
        edits = list_video_edits(root, item_id)
        for record in edits:
            if not record.get('is_stale'):
                paths[record['output_path']] = '編集候補 ' + record.get('edit_id', '')[:8]
                revisions_by_path[record['output_path']] = record['request_revision']
                if record['source_path'] not in paths:
                    paths[record['source_path']] = '編集前の動画'
                    revisions_by_path[record['source_path']] = record['request_revision']
            if record.get('request_revision') != request_revision:
                record['is_stale'] = True
                record['stale_reason'] = '以前の生成指示に基づく編集候補です'
    candidates = [value for path, label in paths.items() if (value := _media(root, path, kind, label))]
    refs = [value for path, label in references.items() if (value := _media(root, path, 'image', label))]
    for candidate in candidates:
        candidate['current'] = True
        candidate['request_revision'] = revisions_by_path.get(candidate['path'], request_revision)
        if kind == 'video':
            parts = Path(candidate['path']).parts
            if len(parts) >= 6 and parts[:3] == ('assets', 'test', 'video_gen_candidates'):
                candidate['request_revision'] = parts[-2]
            try:
                api._assert_current_video_candidate_path(root, item_id, candidate['path'])
                if candidate['path'].startswith('assets/test/video_edits/'):
                    from toc.video_editing import verify_video_edit
                    verify_video_edit(root, candidate['path'], request_revision=request_revision)
            except ValueError:
                candidate['current'] = False
            if candidate['request_revision'] != request_revision:
                candidate['current'] = False
    spatial = _load(root, SPATIAL, {'schema_version': 'spatial_previews_v1', 'revision': 0, 'plans': {}})
    authored_geometry = node.get('cut_contract', {}).get('cinematic_contract', {}).get('execution', {}).get('geometry')
    saved_geometry = spatial.get('plans', {}).get(item_id, {})
    geometry = saved_geometry.get('geometry') or authored_geometry
    geometry_stale = bool(saved_geometry and saved_geometry.get('request_revision') != request_revision)
    notes = candidate_notes.load_notes(root, item_id)
    notes['entries'] = [row for row in notes['entries'] if row['kind'] == kind]
    selected = None
    selection_error = None
    if kind == 'video':
        try:
            selected = selected_video_path(root, item_id, data)
        except (ValueError, FileNotFoundError) as exc:
            selection_error = str(exc)
    return {'runId': root.name, 'run_id': root.name, 'item_id': item_id, 'kind': kind, 'request_revision': request_revision,
        'candidates': candidates, 'references': refs, 'notes': notes, 'variants': variants, 'video_edits': edits,
        'geometry': geometry, 'geometry_revision': spatial['revision'], 'geometry_stale': geometry_stale,
        'geometry_preview': project_geometry(geometry) if geometry else None,
        'allowed_assets': [{'id': key, 'name': value} for key, value in _assets(node, request, data).items()],
        'planned_duration_seconds': node.get('render', {}).get('video_duration_seconds') or generation.get('duration_seconds') or 0,
        'selected_video_path': selected, 'selection_error': selection_error}


def _require_media(ctx, path, sha, *, reference=False, current=False):
    records = ctx['references'] if reference else ctx['candidates']
    record = next((row for row in records if row['path'] == path), None)
    if record is None:
        raise ValueError('対象に属する候補または参照画像を選択してください')
    if record['sha256'] != sha:
        raise ValueError('素材が変更されています。再読み込みしてください')
    if current and not record.get('current', True):
        raise ValueError('以前の生成指示の候補です。現在の候補を選択してください')
    return record


def select_video_path(root, item_id, path, sha):
    api = app()
    ctx = context(root, item_id, 'video')
    record = _require_media(ctx, path, sha, current=True)
    required = max(float(ctx['planned_duration_seconds']), api._narration_min_duration_seconds(root, item_id) or 0)
    if not record.get('duration_seconds') or record['duration_seconds'] + 0.05 < required:
        raise ValueError('編集動画が現在のカット尺またはナレーションより短いため採用できません')
    selected = {'path': path, 'sha256': sha, 'request_revision': ctx['request_revision'], 'selected_at': sound_design.now()}
    if path.startswith('assets/test/video_edits/'):
        from toc.video_editing import verify_video_edit
        receipt = verify_video_edit(root, path, request_revision=ctx['request_revision'])
        selected.update(receipt_path=receipt['receipt_path'], receipt_sha256=_sha(root, receipt['receipt_path']))
    document = _load(root, SELECTIONS, {'schema_version': 'production_selections_v1', 'items': {}})
    prior = document['items'].get(item_id)
    if prior and {k:v for k,v in prior.items() if k != 'selected_at'} == {k:v for k,v in selected.items() if k != 'selected_at'}:
        return
    document['items'][item_id] = selected
    sound_design.write_json(root, SELECTIONS, document)
    api.append_state_snapshot(root / 'state.txt', {'human_choice.video.item': item_id,
        'human_choice.video.path': path, 'human_choice.video.sha256': sha,
        'human_choice.video.at': selected['selected_at'], 'review.final.status': 'changes_requested',
        'slot.p860.status': 'awaiting_approval', 'slot.p860.note': '動画の選択が変わりました。音声設定を確認してください。'})


async def _mutate(req, kind, action):
    api = app()
    root = api.safe_run_dir(req.run_id, api.ROOT)
    try:
        async with api._serialized_run_write(root, 'run_artifacts'):
            await asyncio.to_thread(action, root)
            return await asyncio.to_thread(context, root, req.item_id, kind)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=409 if 'revision conflict' in str(exc) else 400, detail=str(exc)) from exc
    except subprocess.SubprocessError as exc:
        raise HTTPException(status_code=400, detail='ローカル動画処理に失敗しました。元の素材は変更していません。') from exc


async def status(run_id: str, item_id: str, kind: Literal['image', 'video']):
    api = app()
    try:
        return await asyncio.to_thread(context, api.safe_run_dir(run_id, api.ROOT), item_id, kind)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def save_note(req: NoteRequest):
    def action(root):
        ctx = context(root, req.item_id, req.kind)
        candidate = _require_media(ctx, req.candidate_path, req.candidate_sha256)
        candidate_notes.add_note(root, **req.model_dump(exclude={'run_id'}), request_revision=candidate.get('request_revision', ''))
    return await _mutate(req, req.kind, action)


async def make_variant(req: VariantRequest):
    def action(root):
        ctx = context(root, req.item_id, 'image')
        _require_media(ctx, req.base_path, req.base_sha256, reference=True)
        _require_media(ctx, req.edited_path, req.edited_sha256)
        asset_variants.create_variant(root, **req.model_dump(exclude={'run_id'}))
    return await _mutate(req, 'image', action)


async def edit_video(req: EditRequest):
    def action(root):
        from toc.video_editing import create_video_edit, VideoEditSettings
        ctx = context(root, req.item_id, 'video')
        _require_media(ctx, req.source_path, req.source_sha256, current=True)
        create_video_edit(root, item_id=req.item_id, source_path=req.source_path, source_sha256=req.source_sha256,
            request_revision=ctx['request_revision'], settings=VideoEditSettings.model_validate(req.settings))
    return await _mutate(req, 'video', action)


async def select_video(req: SelectRequest):
    return await _mutate(req, 'video', lambda root: select_video_path(root, req.item_id, req.path, req.sha256))


async def save_geometry(req: GeometryRequest):
    def action(root):
        ctx = context(root, req.item_id, req.kind)
        geometry = validate_geometry(req.geometry, {v['id']: v['name'] for v in ctx['allowed_assets']})
        document = _load(root, SPATIAL, {'schema_version': 'spatial_previews_v1', 'revision': 0, 'plans': {}})
        if document['revision'] != req.expected_revision:
            raise ValueError('revision conflict: 配置を再読み込みしてください')
        document['revision'] += 1
        document['plans'][req.item_id] = {'geometry': geometry, 'request_revision': ctx['request_revision'], 'updated_at': sound_design.now()}
        sound_design.write_json(root, SPATIAL, document)
    return await _mutate(req, req.kind, action)


def install(api):
    if not hasattr(api.router, 'add_api_route'):
        return
    api.router.add_api_route(PREFIX, status, methods=['GET'])
    for path, handler in [('notes', save_note), ('variant', make_variant), ('video-edit', edit_video),
                          ('select-video', select_video), ('geometry', save_geometry)]:
        api.router.add_api_route(PREFIX + '/' + path, handler, methods=['POST'])
