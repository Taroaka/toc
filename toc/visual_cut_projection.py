"""Pure visual-only update shared by manual cut editing and scene preparation."""
from copy import deepcopy
import hashlib
import json
from toc.shot_projection import project_cut_shots


def project_visual_cut(parent, plan, resources, *, story_time='', time_of_day='', direction_binding=None):
    projected=project_cut_shots(parent,plan,resources,story_time=story_time,time_of_day=time_of_day)
    allowed={'shot_plan','shots','image_generation'}
    for key in set(parent)|set(projected):
        if key not in allowed and parent.get(key)!=projected.get(key):
            raise ValueError('shot projection changed protected parent field: '+key)
    normalized=projected['shot_plan']
    projected['shot_direction_override']={
        'schema_version':'shot_direction_override_v1',
        'source_direction_binding':deepcopy(direction_binding),
        'authored_cut_id':parent.get('authored_cut_id'),
        'plan_sha256':hashlib.sha256(json.dumps(normalized,ensure_ascii=False,sort_keys=True,
            separators=(',',':'),allow_nan=False).encode()).hexdigest(),
    }
    return projected,normalized
