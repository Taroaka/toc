import { describe, expect, it } from 'vitest';
import {
  canResumeRun,
  isRunRepairing,
  isTerminalRunFailure,
  isWaitingForNarration,
  runFailureMessage,
} from './runStatus';

describe('runStatus', () => {
  it('treats canonical failure as terminal even when the runtime stage was stale running', () => {
    const progress = {
      status: 'FAILED',
      runtimeStage: 'cinematic_authoring_failed',
      failure: { terminal: true, stage: 'p410', message: 'authoring process exited' },
    };

    expect(isTerminalRunFailure(progress)).toBe(true);
    expect(canResumeRun(progress)).toBe(true);
    expect(runFailureMessage(progress)).toBe('authoring process exited');
  });

  it('lets explicit terminal failure win over a stale repairing marker', () => {
    const progress = {
      status: 'FAILED',
      repair: { phase: 'repairing' },
      failure: { terminal: true, stage: 'p410', message: 'repair worker stopped' },
    };

    expect(isTerminalRunFailure(progress)).toBe(true);
    expect(canResumeRun(progress)).toBe(true);
  });

  it('keeps a validation candidate repair active and non-resumable', () => {
    const progress = {
      status: 'AUTHORING',
      runtimeStage: 'cinematic_authoring',
      repair: { phase: 'repairing' },
      currentStage: { state: 'in_progress' },
    };

    expect(isRunRepairing(progress)).toBe(true);
    expect(isTerminalRunFailure(progress)).toBe(false);
    expect(canResumeRun(progress)).toBe(false);
  });

  it.each([
    { status: 'running', runtimeStage: 'scene_images_generating' },
    { status: 'P650', runtimeStage: 'p680_terminal_verification_failed', currentStage: { state: 'failed' } },
  ])('distinguishes active and later-stage stopped states', (progress) => {
    expect(canResumeRun(progress)).toBe(progress.runtimeStage.includes('failed'));
  });

  it('provides a safe fallback when the backend has no diagnostic text', () => {
    expect(runFailureMessage({ failure: { stage: 'p920' } })).toBe('p920 で停止しました');
    expect(runFailureMessage({})).toBe('処理が失敗しました');
  });

  it('allows starting narration from a completed p680 waiting state', () => {
    const progress = {
      status: 'P680',
      runtimeStage: 'scene_images_generated',
      currentStage: { code: 'p710', state: 'pending' },
    };

    expect(isWaitingForNarration(progress)).toBe(true);
    expect(canResumeRun(progress)).toBe(true);
  });

  it.each([
    { status: 'P680', runtimeStage: 'scene_images_generated', currentStage: { code: 'p710', state: 'done' } },
    { status: 'P680', runtimeStage: 'scene_images_generating', currentStage: { code: 'p710', state: 'pending' } },
    { status: 'P680', runtimeStage: 'scene_images_generated', currentStage: { code: 'p730', state: 'pending' } },
    { status: 'P680', runtimeStage: 'scene_images_generated', repair: { phase: 'repairing' }, currentStage: { code: 'p710', state: 'pending' } },
  ])('does not treat non-waiting states as narration waiting', (progress) => {
    expect(isWaitingForNarration(progress)).toBe(false);
  });
});
