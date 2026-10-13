"""Explicit, versioned shot choices. No taste scoring or inferred acting."""
from copy import deepcopy
import math
import re

SCHEMA = 'shot_direction_v1'
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')


def _error(field):
    raise ValueError('shot_direction:' + field)


def _object(value, keys, field):
    if not isinstance(value, dict) or set(value) - set(keys):
        _error(field + ':object_or_unknown_field')
    return value


def _text(value, field, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _error(field + ':text_required')
    return value.strip()


def _number(value, field, minimum=0):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    if not valid:
        _error(field + ':number_required')
    return value


def _list(value, field):
    if not isinstance(value, list):
        _error(field + ':list_required')
    return value


def parent_duration_seconds(cut):
    """Use the adopted render/audio interval before the original authored budget."""
    render = cut.get('render') if isinstance(cut.get('render'), dict) else {}
    video = cut.get('video_generation') if isinstance(cut.get('video_generation'), dict) else {}
    for value in (render.get('video_duration_seconds'), video.get('duration_seconds'),
                  cut.get('duration_seconds'), cut.get('target_duration_seconds')):
        if value is not None:
            return _number(value, 'parent_duration', 0.001)
    _error('parent_duration_required')


def _entity(value, ids, field, nullable=False):
    value = _text(value, field, nullable)
    if value is not None and value not in ids:
        _error(field + ':unknown_entity:' + value)
    return value


def _view(value, characters, objects, field):
    value = _object(value, ('description', 'subjects', 'framing', 'composition', 'focus', 'state_source'), field)
    result = {key: _text(value.get(key), field + '.' + key) for key in ('description', 'framing', 'composition')}
    result['focus'] = _text(value.get('focus'), field + '.focus', True)
    if value.get('state_source') not in (None, 'start', 'result', 'previous_end'):
        _error(field + ':state_source')
    result['state_source'] = value.get('state_source')
    subjects, seen = [], set()
    for item in _list(value.get('subjects'), field + '.subjects'):
        item = _object(item, ('entity_id', 'kind', 'member_id', 'visible_parts', 'view'), field + '.subject')
        if item.get('kind') not in ('character', 'object'):
            _error(field + ':subject_kind')
        entity = _entity(item.get('entity_id'), characters if item['kind'] == 'character' else objects, field)
        member = _text(item.get('member_id'), field + '.member', True)
        key = (item['kind'], entity, member)
        if key in seen:
            _error(field + ':duplicate_subject')
        seen.add(key)
        parts = [_text(p, field + '.part') for p in _list(item.get('visible_parts', []), field + '.parts')]
        subjects.append(dict(entity_id=entity, kind=item['kind'], member_id=member,
                             visible_parts=parts, view=_text(item.get('view'), field + '.view')))
    result['subjects'] = subjects
    return result


def normalize_shot_plan(plan, *, character_ids, object_ids, duration_seconds):
    """Normalize optional artistic fields; reject unresolved identity/timeline data."""
    _object(plan, ('schema_version', 'intent', 'shots'), 'plan')
    if plan.get('schema_version') != SCHEMA:
        _error('schema_version')
    duration = _number(duration_seconds, 'duration', 0.001)
    characters, objects = set(character_ids), set(object_ids)
    rows, seen, cursor = [], set(), 0.0
    for raw in _list(plan.get('shots'), 'shots'):
        _object(raw, ('shot_id', 'start_seconds', 'duration_seconds', 'intent', 'initial_view', 'motion',
                      'camera', 'performance', 'events', 'end_view', 'end_state'), 'shot')
        sid = _text(raw.get('shot_id'), 'shot_id')
        if not _ID.fullmatch(sid) or sid.casefold() in seen:
            _error('duplicate_or_invalid_shot_id')
        seen.add(sid.casefold())
        start = _number(raw.get('start_seconds'), sid + '.start')
        length = _number(raw.get('duration_seconds'), sid + '.duration', 0.001)
        if not math.isclose(start, cursor, abs_tol=1e-6, rel_tol=0):
            _error(sid + ':timeline_gap_or_overlap')
        cursor = start + length
        camera = _object(raw.get('camera'), ('movement', 'angle', 'lens_mm', 'focus_change'), sid + '.camera')
        lens = camera.get('lens_mm')
        if lens is not None:
            _number(lens, sid + '.lens_mm', 0.001)
        performances = []
        for item in _list(raw.get('performance', []), sid + '.performance'):
            _object(item, ('actor_id', 'member_id', 'target_id', 'objective', 'emotion', 'basis', 'behavior', 'trigger'), sid + '.performance')
            basis = item.get('basis')
            if basis not in ('source_action', 'user_direction', 'directorial_interpretation'):
                _error(sid + ':performance_basis')
            performances.append({
                'actor_id': _entity(item.get('actor_id'), characters, sid + '.actor'),
                'member_id': _text(item.get('member_id'), sid + '.member', True),
                'target_id': _entity(item.get('target_id'), characters | objects, sid + '.target', True),
                'basis': basis, 'behavior': _text(item.get('behavior'), sid + '.behavior'),
                **{key: _text(item.get(key), sid + '.' + key, True) for key in ('objective', 'emotion', 'trigger')},
            })
        events = []
        for item in _list(raw.get('events', []), sid + '.events'):
            _object(item, ('kind', 'entity_ids', 'description', 'trigger'), sid + '.event')
            if item.get('kind') not in ('enter_frame', 'leave_frame', 'camera_reveal', 'focus_change', 'transform'):
                _error(sid + ':event_kind')
            ids = [_entity(i, characters | objects, sid + '.event') for i in _list(item.get('entity_ids'), sid + '.event.ids')]
            if not ids or len(ids) != len(set(ids)):
                _error(sid + ':event_ids_required_or_duplicate')
            events.append(dict(kind=item['kind'], entity_ids=ids,
                               description=_text(item.get('description'), sid + '.event.description'),
                               trigger=_text(item.get('trigger'), sid + '.event.trigger', True)))
        initial = _view(raw.get('initial_view'), characters, objects, sid + '.initial')
        end = None if raw.get('end_view') is None else _view(raw['end_view'], characters, objects, sid + '.end')
        initial_ids = {s['entity_id'] for s in initial['subjects']}
        revealed = {i for event in events if event['kind'] in ('enter_frame', 'camera_reveal', 'transform') for i in event['entity_ids']}
        if end and {s['entity_id'] for s in end['subjects']} - initial_ids - revealed:
            _error(sid + ':end_subject_without_presentation_event')
        rows.append(dict(shot_id=sid, start_seconds=start, duration_seconds=length,
            intent=_text(raw.get('intent'), sid + '.intent'), initial_view=initial,
            motion=_text(raw.get('motion'), sid + '.motion'),
            camera={'movement': _text(camera.get('movement'), sid + '.camera.movement'),
                    'angle': _text(camera.get('angle'), sid + '.camera.angle', True), 'lens_mm': lens,
                    'focus_change': _text(camera.get('focus_change'), sid + '.camera.focus_change', True)},
            performance=performances, events=events, end_view=end,
            end_state=_text(raw.get('end_state'), sid + '.end_state')))
    if not rows or len(rows) > 60 or not math.isclose(cursor, duration, abs_tol=1e-6, rel_tol=0):
        _error('timeline_total_mismatch')
    return {'schema_version': SCHEMA, 'intent': _text(plan.get('intent'), 'intent'), 'shots': rows}


SHOT_PLAN_FORMAT = {
    'schema_version': SCHEMA, 'intent': 'このcutで何を届けたいか。選んだ意図だけ',
    'shots': [{
        'shot_id': '安定したASCII ID', 'start_seconds': 'cut内開始秒。先頭0、前shotの終了と一致',
        'duration_seconds': '秒数。全shot合計=cut尺。通常速度の行為を選び、1shotは15秒以下',
        'intent': '前後のcutと比べて、この画で注目させること',
        'initial_view': {'description': '開始瞬間の画。将来の結果や参加者全員を詰めない',
            'subjects': [{'entity_id': 'cutのcharacter_idsまたはobject_idsから選ぶ', 'kind': 'character|object',
                'member_id': None, 'visible_parts': ['必要なら顔/手/足/背中など。全身に限定しない'],
                'view': '向き、画に見える範囲、遮蔽'}],
            'framing': '見せる距離と範囲', 'composition': '配置と画角', 'focus': '注視点、指定不要ならnull',
            'state_source': 'start|result|previous_end|null。nullはその時点までの状態継承。previous_endは直前shotの終了画を参照。resultは根拠ある変化後だけ'},
        'motion': 'このshotの行為・静止・環境変化。顔の見えない画に表情を要求しない',
        'camera': {'movement': '固定または具体的なカメラ動作。人物の移動と区別',
            'angle': None, 'lens_mm': None, 'focus_change': None},
        'performance': [{'actor_id': '人物ID', 'member_id': None, 'target_id': None,
            'objective': '相手や自分に何を望むか。不要ならnull', 'emotion': None,
            'basis': 'source_action|user_direction|directorial_interpretation',
            'behavior': '作者が選んだ観察可能な演技', 'trigger': None}],
        'events': [{'kind': 'enter_frame|leave_frame|camera_reveal|focus_change|transform',
            'entity_ids': ['人物/物ID'], 'description': '画面への入り方/変化', 'trigger': None}],
        'end_view': '必要ならinitial_viewと同型の終了画像の構図。不要ならnull',
        'end_state': '保持/継続/退出と到達する状態',
    }],
}

SHOT_AUTHOR_GUIDANCE = '''
cutのshot_planはshot_direction_v1で執筆します。自由に構成を考えた後、選んだ意図と実行条件を記録します。
character_ids/object_idsはこの新版cut全体の参加者です。開始画は各shot.initial_view.subjectsだけ。
世界に存在することと、画角に見えること、見せる身体部分を分けます。画面外を不存在としません。
参加者全員、顔、全身、手足、道具、動作の前提を開始画へ並べる必要はありません。
必要な人物の目的・感情から、相手への働きかけと反応の契機を作者が選びます。感情→定型gestureにしません。
目的はsource_action/user_direction/directorial_interpretationを区別。解釈を原作の心理事実へ昇格させません。
前後の画角、向き、視線、運動、間を考慮し、足元・背中・環境だけも選べます。毎cut違う撮影を義務にしません。
静止や反復も選択可能です。cameraを固定することと人物の身体を止めることは別です。
ひとつのcut内を必要なら複数shotへ分けます。最初0秒、隙間や重なりなし、合計はcut尺と一致。
APIで各shotを個別生成して結合します。ネイティブの複数shot生成は使いません。各shotは15秒以下。
途中で姿を見せる人物にはenter_frame/camera_reveal等を結び、必要な終了画像end_viewにその同一人物を含めます。
途中だけ現れ終了画にもいない人物は、この入力方式で参照できないためshotを分けて開始画像でidentityを担保します。
変身の世界上の状態変化は原作・state_variantと対応させ、単にカメラで見えることと区別します。
subject/performance/eventsが不要なら[]、感情・相手・レンズ・焦点移動・終了構図が不要ならnull。
nullは未解決の素材IDや時間の代用ではありません。既存の音声が採用済みなら原稿と音声区間を変更しません。
'''
