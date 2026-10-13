import { describe, expect, it } from 'vitest';
import { buildCutDirectionSavePayload, cutItemIdForDirectionSelection, cutMatchesId, type CutDirectionCut } from './CutDirectionPanel';

const revision = 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

describe('cut direction save payload', () => {
  it('sends only the structured plan when that mode is selected', () => {
    expect(buildCutDirectionSavePayload({
      runId: 'run-a', itemId: 'scene1_cut1', expectedRevision: revision, mode: 'plan',
      value: '{"intent":"手元を見せる"}',
    })).toEqual({
      run_id: 'run-a', item_id: 'scene1_cut1', expected_revision: revision,
      plan: { intent: '手元を見せる' },
    });
  });

  it('sends only a natural instruction when that mode is selected', () => {
    expect(buildCutDirectionSavePayload({
      runId: 'run-a', itemId: 'scene1_cut1', expectedRevision: revision, mode: 'instruction',
      value: '  顔を映さずに手元へ寄る  ',
    })).toEqual({
      run_id: 'run-a', item_id: 'scene1_cut1', expected_revision: revision,
      instruction: '顔を映さずに手元へ寄る',
    });
  });

  it('rejects invalid plan JSON, non-object JSON, and blank instructions', () => {
    const base = { runId: 'run-a', itemId: 'cut1', expectedRevision: revision };
    expect(() => buildCutDirectionSavePayload({ ...base, mode: 'plan', value: '{' })).toThrow('JSONを確認');
    expect(() => buildCutDirectionSavePayload({ ...base, mode: 'plan', value: '[]' })).toThrow('JSONオブジェクト');
    expect(() => buildCutDirectionSavePayload({ ...base, mode: 'instruction', value: '  ' })).toThrow('指示を入力');
  });
});

describe('shot cut selection', () => {
  const cut: CutDirectionCut = {
    id: 'scene10_cut01',
    cutId: 'scene10_cut01',
    intent: 'A witness enters after the door opens',
    durationSeconds: 8,
    narrationDurationSeconds: 7,
    thumbnailPath: null,
    plan: { schema_version: 'shot_direction_v1' },
    shots: [{
      id: 'scene10_cut01_shotsh01',
      startSeconds: 0,
      durationSeconds: 4,
      intent: 'Hold on the door',
      framing: 'Close-up',
      visibleSubjects: [],
      motion: 'The door opens',
      referencePaths: [],
      imagePath: null,
      videoPath: null,
    }],
    source: 'shot_direction_v1',
  };

  it('matches a selected child item to its parent shot plan by exact ID', () => {
    const childItemId = 'scene10_cut01_shotsh01';
    expect(cutMatchesId(cut, childItemId)).toBe(true);
    expect(cutMatchesId(cut, 'scene10_cut01_shotsh02')).toBe(false);
    expect(cutItemIdForDirectionSelection(cut, new Set([childItemId]))).toBe(childItemId);
  });

  it('selects the first visible child when a parent shot plan is chosen', () => {
    const firstChild = 'scene10_cut01_shotsh01';
    const secondChild = 'scene10_cut01_shotsh02';
    expect(cutItemIdForDirectionSelection(cut, new Set([firstChild, secondChild]))).toBe(firstChild);
    expect(cutItemIdForDirectionSelection(cut, new Set(['scene10_cut01']))).toBe('scene10_cut01');
    expect(cutItemIdForDirectionSelection(cut, new Set())).toBeNull();
  });
});
