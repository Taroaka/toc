"""Freeze one authored variant/event selection without discarding source research."""
from __future__ import annotations

from collections.abc import Mapping

CONTRACT = 'story_event_selection_v1'


class StorySelectionError(ValueError):
    pass


def _ids(value, field):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise StorySelectionError(f'story.selection.{field}_invalid')
    if len(value) != len(set(value)):
        raise StorySelectionError(f'story.selection.{field}_duplicate')
    return value


def selected_event_order(document: Mapping, registry: Mapping) -> list[str]:
    """Resolve the coverage universe. Legacy single-source documents keep their contract."""
    events = registry.get('events', {})
    order = list(registry.get('event_order', events))
    variants = registry.get('variants', {})
    selection = document.get('selection') or {}
    if not isinstance(selection, Mapping):
        raise StorySelectionError('story.selection.invalid')
    marker = selection.get('event_selection_contract')
    if 'event_selection_contract' not in selection:
        if 'selected_event_ids' in selection:
            raise StorySelectionError('story.selection.contract_required')
        if len(variants) > 1:
            raise StorySelectionError('story.selection.required: choose one widely familiar version and selected_event_ids')
        return order
    if marker != CONTRACT:
        raise StorySelectionError('story.selection.contract_invalid')
    chosen_variants = _ids(selection.get('selected_variant_ids'), 'variant_ids')
    if variants:
        if len(chosen_variants) != 1 or chosen_variants[0] not in variants:
            raise StorySelectionError('story.selection.single_known_variant_required')
    elif chosen_variants:
        raise StorySelectionError('story.selection.unknown_variant')
    chosen = _ids(selection.get('selected_event_ids'), 'event_ids')
    if not chosen or any(eid not in events for eid in chosen):
        raise StorySelectionError('story.selection.known_events_required')
    for key in ('selection_rationale', 'familiarity_basis'):
        if not isinstance(selection.get(key), str) or not selection[key].strip():
            raise StorySelectionError(f'story.selection.{key}_required')

    eligible = set(order)
    if chosen_variants:
        vid = chosen_variants[0]
        variant = variants[vid]
        declared = variant.get('event_ids', []) if isinstance(variant, Mapping) else []
        if not isinstance(declared, (list, tuple)) or any(not isinstance(eid, str) for eid in declared) or len(declared) != len(set(declared)):
            raise StorySelectionError('story.selection.variant_event_ids_invalid')
        eligible = set()
        for eid, event in events.items():
            membership = event.get('variant_ids', []) if isinstance(event, Mapping) else []
            # Explicit event membership wins over a contradictory variant index.
            if not isinstance(membership, (list, tuple)):
                if eid in chosen:
                    raise StorySelectionError('story.selection.variant_membership_invalid')
                continue
            declared_here = eid in declared if isinstance(declared, (list, tuple)) else False
            if eid in chosen and membership and isinstance(variant, Mapping) and 'event_ids' in variant and isinstance(declared, (list, tuple)) and ((vid in membership) != declared_here):
                raise StorySelectionError('story.selection.variant_membership_conflict')
            if (membership and vid in membership) or (not membership and declared_here):
                eligible.add(eid)
        # Old single-version research need not have annotated membership.
        if len(variants) == 1 and not eligible and not declared and all(
            not event.get('variant_ids') for event in events.values() if isinstance(event, Mapping)
        ):
            eligible = set(order)
        if not set(chosen) <= eligible:
            raise StorySelectionError('story.selection.event_outside_selected_variant')
        if isinstance(declared, (list, tuple)) and set(chosen) <= set(declared):
            order = list(declared)

    if chosen != [eid for eid in order if eid in set(chosen)]:
        raise StorySelectionError('story.selection.event_order_invalid')

    omissions = selection.get('omitted_events', [])
    if not isinstance(omissions, list):
        raise StorySelectionError('story.selection.omitted_events_invalid')
    omitted_ids = []
    for item in omissions:
        if not isinstance(item, Mapping) or item.get('event_id') not in events or not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise StorySelectionError('story.selection.omission_reason_required')
        if item['event_id'] not in eligible:
            raise StorySelectionError('story.selection.omitted_event_outside_variant')
        omitted_ids.append(item['event_id'])
    if len(omitted_ids) != len(set(omitted_ids)) or set(chosen) & set(omitted_ids):
        raise StorySelectionError('story.selection.omissions_overlap')
    if not (eligible - set(chosen)) <= set(omitted_ids):
        raise StorySelectionError('story.selection.omission_reason_required')
    return chosen
