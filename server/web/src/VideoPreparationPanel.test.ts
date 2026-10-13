import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  buildVideoPreparationCancelBody,
  buildVideoPreparationRequestBody,
  canCancelVideoPreparation,
  VideoPreparationSummary,
  type VideoPreparationDto,
} from './VideoPreparationPanel';
import { describe, expect, it } from 'vitest';

describe('video preparation summary', () => {
  it('shows scene status and its reason without exposing operation identifiers', () => {
    const data: VideoPreparationDto = {
      runId: 'run-a',
      enabled: false,
      operationId: 'internal-op-123',
      status: 'needs_input',
      scenes: [{
        sceneId: 'scene01',
        status: 'needs_input',
        reason: '画像費用の見積もりを設定してください',
        changedCuts: ['scene01_cut01'],
        imageCount: 2,
      }],
    };

    const html = renderToStaticMarkup(React.createElement(VideoPreparationSummary, { data }));

    expect(html).toContain('確認が必要');
    expect(html).toContain('準備はまだ有効になっていません');
    expect(html).toContain('画像費用の見積もりを設定してください');
    expect(html).toContain('変更対象 1 cut');
    expect(html).toContain('画像 2枚');
    expect(html).not.toContain('internal-op-123');
  });
});

describe('video preparation request body', () => {
  it('sends explicit limits and nonempty run-relative fixed image paths', () => {
    expect(buildVideoPreparationRequestBody({
      runId: 'run-a',
      maxImageGenerations: 3,
      maxCostUsd: 1.25,
      fixedImagePathsText: ' images/start.png\n\n scenes/scene01/ref.webp  ',
    })).toEqual({
      run_id: 'run-a',
      max_image_generations: 3,
      max_cost_usd: 1.25,
      fixed_image_paths: ['images/start.png', 'scenes/scene01/ref.webp'],
    });
  });

  it('preserves an explicitly selected current setting or sends the selected Standard model', () => {
    const base = {
      runId: 'run-a',
      maxImageGenerations: 1,
      maxCostUsd: 2,
      fixedImagePathsText: '',
    };
    const commonBody = {
      run_id: 'run-a',
      max_image_generations: 1,
      max_cost_usd: 2,
      fixed_image_paths: [],
    };

    expect(buildVideoPreparationRequestBody({ ...base, targetVideoModel: null })).toEqual({
      ...commonBody,
      target_video_model: null,
    });
    expect(buildVideoPreparationRequestBody({ ...base, targetVideoModel: 'higgsfield_kling_standard' })).toEqual({
      ...commonBody,
      target_video_model: 'higgsfield_kling_standard',
    });
  });
});

describe('video preparation cancellation', () => {
  it('is available only while the operation is running', () => {
    expect(canCancelVideoPreparation('running')).toBe(true);
    expect(canCancelVideoPreparation('idle')).toBe(false);
    expect(canCancelVideoPreparation('completed')).toBe(false);
    expect(canCancelVideoPreparation('needs_input')).toBe(false);
    expect(canCancelVideoPreparation('failed')).toBe(false);
  });

  it('sends the current run id in the cancel request body', () => {
    expect(buildVideoPreparationCancelBody('run-a')).toEqual({ run_id: 'run-a' });
  });
});
