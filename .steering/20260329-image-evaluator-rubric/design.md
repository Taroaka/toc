# Design

## Rubric

初期 rubric は次の 5 criterion とする。

- `story_alignment`
- `subject_specificity`
- `prompt_craft`
- `continuity_readiness`
- `production_readiness`

## Weighting

- `story_alignment`: 0.30
- `subject_specificity`: 0.25
- `prompt_craft`: 0.15
- `continuity_readiness`: 0.15
- `production_readiness`: 0.15

## Contract

`image_generation.contract` に配置する。

```yaml
contract:
  target_focus: "character|relationship|setpiece|blocking|environment"
  must_include: []
  must_avoid: []
  done_when: []
```

## Review metadata

`image_generation.review` は以下を持つ。

- `agent_review_ok`
- `agent_review_reason_keys`
- `agent_review_reason_messages`
- `human_review_ok`
- `human_review_reason`
- `rubric_scores`
- `overall_score`

## Additional reason keys

- `image_contract_missing`
- `image_contract_must_include_unmet`
- `image_contract_must_avoid_violated`
- `image_contract_target_focus_unmet`
- `image_prompt_story_alignment_weak`
- `image_prompt_subject_specificity_weak`
- `image_prompt_continuity_weak`
- `image_prompt_production_readiness_weak`
