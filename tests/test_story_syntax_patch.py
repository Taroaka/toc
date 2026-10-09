import json
import pytest
from toc.story_syntax_patch import apply_syntax_edits, SyntaxPatchError, build_syntax_prompt, SYNTAX_EDIT_SCHEMA


def test_missing_comma_changes_no_content():
    raw='{"name":"本文" "id":2}'
    position=raw.index(' "id"')
    fixed=apply_syntax_edits(raw,{'edits':[{'start':position,'end':position,'replacement':','}]})
    assert json.loads(fixed)=={'name':'本文','id':2}


@pytest.mark.parametrize('raw,edit', [
    ('{"id":1}', {'start':6,'end':7,'replacement':'2'}),
    ('{"a":"x,y"}', {'start':7,'end':8,'replacement':''}),
    ('{"a":1}', {'start':0,'end':1,'replacement':'['}),
])
def test_syntax_repair_cannot_change_values_strings_or_structure(raw,edit):
    with pytest.raises(SyntaxPatchError): apply_syntax_edits(raw,{'edits':[edit]})


def test_syntax_prompt_does_not_replay_the_story_task():
    prompt=build_syntax_prompt('{"a":1,}',{'line':1,'column':8,'offset':7,'message':'bad comma'})
    assert 'syntax' in prompt.lower()
    assert 'scene_plan' not in prompt
    assert SYNTAX_EDIT_SCHEMA['additionalProperties'] is False
