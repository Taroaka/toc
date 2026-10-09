"""Authored film language and observable shot execution, without taste scoring."""
from copy import deepcopy
import hashlib
import json

FILM_SCHEMA = 'film_language_v1'
EXECUTION_SCHEMA = 'cinematic_execution_v1'
FILM_FIELDS = ('palette', 'lighting', 'exposure', 'optics', 'texture', 'composition', 'camera')
LABELS = dict(palette='色調', lighting='照明方針', exposure='明暗', optics='光学的な見え方',
              texture='素材の質感', composition='構図方針', camera='撮影者の振る舞い')
EXECUTION_FORMAT = {
    'light_continuity': '光源・届く範囲・陰影について動画の間も維持する具体的条件。不要なら空文字',
    'focus': {'initial': '開始画の焦点対象と深度', 'change': '必要な時だけ焦点を移す契機と対象。それ以外は空文字'},
    'performance': {'action': '原作の行為をどう演じるか', 'observable_reaction': '視線・呼吸・表情の観察可能な変化', 'timing': '反応の間と順序'},
    'physics': ['接触・重さ・摩擦・抵抗・動いた後の収まり。必要なものだけ'],
    'geometry': {'schema_version': 'shot_geometry_v1',
        'camera': {'position': ['x m', 'y m', 'z m'], 'target': ['x m', 'y m', 'z m'],
                   'vertical_fov_degrees': '数値', 'aspect_ratio': '幅/高さの数値'},
        'subjects': [{'asset_id': 'このcutの人物・物・場所ID', 'name': '表示名',
                      'position': ['中心x m', '中心y m', '中心z m'], 'size': ['幅m', '奥行m', '高さm']}],
        'lights': [{'name': '既存光源の名前', 'position': ['x m', 'y m', 'z m'], 'range_m': '図示用レンジの数値'}]},
    'native_audio': {'mode': 'off|natural_sound|dialogue_and_sound', 'sound_events': ['原作の画面内外の音と発生する契機'],
        'dialogue': [{'speaker_id': 'cutの人物ID', 'text': '原作に根拠ある正確な台詞',
            'source_beat_ids': ['このcutのbeat ID'], 'source_quote': '参照beat.dialogue[].textの発話原文。textはこの原文のまま使う',
            'delivery': '発声と息の指示', 'timing': '発話する契機'}]},
}


def _text(value, field, *, empty=True):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f'cinematic:{field}:text_required')
    return value.strip()


def _mapping(value, field):
    if not isinstance(value, dict):
        raise ValueError(f'cinematic:{field}:object_required')
    return value


def _strings(value, field):
    if not isinstance(value, list):
        raise ValueError(f'cinematic:{field}:list_required')
    return [_text(v, field, empty=False) for v in value]


def validate_film_language(film):
    _mapping(film, 'film_language')
    if film.get('schema_version') != FILM_SCHEMA:
        raise ValueError('cinematic:film_language:unknown_version')
    _text(film.get('intent'), 'intent', empty=False)
    fields = _mapping(film.get('fields'), 'fields')
    if not fields or set(fields) - set(FILM_FIELDS):
        raise ValueError('cinematic:film_language:unknown_or_empty_fields')
    for key, value in fields.items():
        _text(value, key, empty=False)
    for key, value in _mapping(film.get('voices', {}), 'voices').items():
        _text(key, 'voice_identity', empty=False)
        _text(value, 'voice_description', empty=False)
    return film


def resolve_film_language(film, scene_overrides=None, cut_overrides=None):
    validate_film_language(film)
    fields = deepcopy(film['fields'])
    origins = {key: 'film' for key in fields}
    for scope, overrides in (('scene', scene_overrides), ('cut', cut_overrides)):
        for key, value in _mapping(overrides or {}, scope).items():
            if key not in FILM_FIELDS:
                raise ValueError(f'cinematic:{scope}:unknown_field:{key}')
            if value is None:
                fields.pop(key, None); origins[key] = scope + ':clear'
            elif _text(value, key):
                fields[key] = value.strip(); origins[key] = scope
    sha = hashlib.sha256(json.dumps(film, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {'schema_version': 'effective_film_language_v1', 'fields': fields, 'origins': origins, 'film_sha256': sha}


def normalize_native_audio(value, *, characters=None, beats=None, resources=None, voices=None, source_beats=None):
    value = deepcopy(_mapping(value, 'native_audio'))
    if set(value) - {'mode', 'sound_events', 'dialogue'}:
        raise ValueError('cinematic:native_audio:unknown_field')
    mode = value.get('mode', 'off')
    if mode not in ('off', 'natural_sound', 'dialogue_and_sound'):
        raise ValueError('cinematic:native_audio:mode_invalid')
    events = _strings(value.get('sound_events', []), 'sound_events')
    lines = value.get('dialogue', [])
    if not isinstance(lines, list):
        raise ValueError('cinematic:dialogue:list_required')
    if (mode == 'off' and (events or lines)) or (mode != 'dialogue_and_sound' and lines):
        raise ValueError('cinematic:native_audio:mode_content_conflict')
    if mode == 'dialogue_and_sound' and not lines:
        raise ValueError('cinematic:dialogue:lines_required')
    for line in lines:
        _mapping(line, 'dialogue_line')
        speaker = _text(line.get('speaker_id'), 'speaker', empty=False)
        if characters is not None and speaker not in characters:
            raise ValueError('cinematic:dialogue:speaker_not_in_cut')
        refs = _strings(line.get('source_beat_ids', []), 'dialogue_beats')
        if not refs or (beats is not None and not set(refs) <= set(beats)):
            raise ValueError('cinematic:dialogue:source_beat_required')
        _text(line.get('text'), 'dialogue_text', empty=False)
        if source_beats is not None:
            quote = _text(line.get('source_quote'), 'dialogue_source_quote', empty=False)
            speaker_names = {speaker}
            if resources is not None:
                speaker_names.add(resources['characters'][speaker]['name'])
            evidence = [speech for row in source_beats if row.get('beat_id') in refs
                        for speech in (row.get('dialogue') if isinstance(row.get('dialogue'), list) else [])
                        if isinstance(speech, dict)]
            if line['text'] != quote or not any(speech.get('text') == quote and
                    (speech.get('speaker_id') or speech.get('speaker')) in speaker_names for speech in evidence):
                raise ValueError('cinematic:dialogue:source_quote_mismatch')
        for key in ('delivery', 'timing'):
            _text(line.get(key, ''), key)
        if resources is not None:
            line['speaker_name'] = resources['characters'][speaker]['name']
            line['voice'] = (voices or {}).get(speaker, '')
    return {'mode': mode, 'sound_events': events, 'dialogue': lines}


def execution_from_cut(cut, *, film=None, scene_overrides=None, resources=None, source_beats=None):
    raw = deepcopy(cut.get('execution', {}))
    _mapping(raw, 'execution')
    allowed = {'light_continuity', 'focus', 'performance', 'physics', 'native_audio', 'geometry'}
    if set(raw) - allowed:
        raise ValueError('cinematic:execution:unknown_field')
    camera = _mapping(cut.get('camera', {}), 'camera')
    focus = _mapping(raw.get('focus', {}), 'focus')
    performance = _mapping(raw.get('performance', {}), 'performance')
    if set(focus) - {'initial', 'change'} or set(performance) - {'action', 'observable_reaction', 'timing'}:
        raise ValueError('cinematic:execution:unknown_field')
    if cut.get('cut_role') == 'sub' and performance:
        raise ValueError('cinematic:unpeopled_performance')
    result = {'schema_version': EXECUTION_SCHEMA,
        'light_continuity': _text(raw.get('light_continuity', camera.get('light', '')), 'light_continuity'),
        'focus': {key: _text(value, 'focus.' + key) for key, value in focus.items()},
        'performance': {key: _text(value, 'performance.' + key) for key, value in performance.items()},
        'physics': _strings(raw.get('physics', []), 'physics'),
        'native_audio': normalize_native_audio(raw.get('native_audio', {'mode': 'off'}),
            characters=cut.get('character_ids', []), beats=cut.get('source_beat_ids', []), resources=resources,
            voices=film.get('voices', {}) if film else {}, source_beats=source_beats)}
    if film:
        result['film_language'] = resolve_film_language(film, scene_overrides, cut.get('film_language_overrides'))
        # Film camera language guides the author. The concrete authored movement
        # owns execution; never append a conflicting global move after it.
        if camera.get('movement'):
            result['film_language']['fields']['camera'] = camera['movement']
            result['film_language']['origins']['camera'] = 'cut.camera.movement'
    if 'geometry' in raw:
        from toc.spatial_previs import validate_geometry
        allowed_assets = None
        if resources is not None:
            ids = set(cut.get('character_ids', []) + cut.get('object_ids', []) + [cut.get('location_id')])
            allowed_assets = {key: value['name'] for group in ('characters', 'objects', 'locations')
                              for key, value in resources.get(group, {}).items() if key in ids}
        result['geometry'] = validate_geometry(raw['geometry'], allowed_assets)
    return result


def language_text(effective, *, image=False):
    fields = effective.get('fields', {})
    return '\n'.join(f'{LABELS[key]}: {fields[key]}' for key in FILM_FIELDS
                     if fields.get(key) and key != 'camera')


def video_execution_fragments(execution):
    if execution.get('schema_version') != EXECUTION_SCHEMA:
        raise ValueError('cinematic:execution:unknown_version')
    audio = normalize_native_audio(execution.get('native_audio', {'mode': 'off'}))
    sound = []
    if audio['mode'] != 'off':
        sound = ['画面に同期する音: ' + '。'.join(audio['sound_events'])] if audio['sound_events'] else []
        sound.append('音楽や劇伴を生成しない。指定のない台詞や声を追加しない。')
        for line in audio['dialogue']:
            name = _text(line.get('speaker_name'), 'speaker_name', empty=False)
            sound.append(f'{name}の台詞「{line["text"]}」。{line.get("voice", "")}。{line.get("delivery", "")}。{line.get("timing", "")}。口の動きと発声を同期させる。')
    focus = execution.get('focus', {})
    geometry = ''
    if execution.get('geometry'):
        from toc.spatial_previs import geometry_prompt
        geometry = geometry_prompt(execution['geometry'])
    return {'start_state': geometry,
        'continuity': '\n'.join(v for v in [language_text(execution.get('film_language', {})), execution.get('light_continuity', '')] if v),
        'camera_motion': '\n'.join(v for v in [focus.get('initial', ''), focus.get('change', '')] if v),
        'emotional_change': '\n'.join(execution.get('performance', {}).values()),
        'primary_motion': '\n'.join(execution.get('physics', [])),
        'environment_motion': '\n'.join(sound)}
