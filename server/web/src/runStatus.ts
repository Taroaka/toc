export type RunStatusProjection = {
  status?: string | null;
  runtimeStage?: string | null;
  repair?: { phase?: string | null } | null;
  currentStage?: { code?: string | null; state?: string | null } | null;
  failure?: {
    terminal?: boolean;
    stage?: string | null;
    message?: string | null;
    runtimeStage?: string | null;
  } | null;
};

const TERMINAL_FAILURE_STATUSES = new Set(['failed', 'failure', 'error', 'aborted', 'interrupted']);
const STOPPED_STATUSES = new Set(['failed', 'failure', 'error', 'aborted', 'interrupted', 'paused', 'blocked', 'stopped']);
const NARRATION_WAITING_SLOT_STATES = new Set(['pending', 'not_started']);

export function isRunRepairing(progress: RunStatusProjection | null | undefined): boolean {
  return String(progress?.repair?.phase || '').trim().toLowerCase() === 'repairing';
}

export function isTerminalRunFailure(progress: RunStatusProjection | null | undefined): boolean {
  if (!progress) return false;
  const status = String(progress.status || '').trim().toLowerCase();
  // A stale repair marker can survive a failed worker.  Explicit canonical
  // terminal evidence wins over that marker.
  if (progress.failure?.terminal === true || TERMINAL_FAILURE_STATUSES.has(status)) return true;
  if (isRunRepairing(progress)) return false;
  const runtimeStage = String(progress.runtimeStage || progress.failure?.runtimeStage || '').trim().toLowerCase();
  if (runtimeStage.includes('failed') || runtimeStage.includes('error')) return true;
  return String(progress.currentStage?.state || '').trim().toLowerCase() === 'failed';
}

export function canResumeRun(progress: RunStatusProjection | null | undefined): boolean {
  if (!progress) return false;
  if (isTerminalRunFailure(progress)) return true;
  if (isRunRepairing(progress)) return false;
  if (isWaitingForNarration(progress)) return true;
  return STOPPED_STATUSES.has(String(progress.status || '').trim().toLowerCase());
}

export function isWaitingForNarration(progress: RunStatusProjection | null | undefined): boolean {
  if (!progress || isRunRepairing(progress) || isTerminalRunFailure(progress)) return false;
  return String(progress.status || '').trim().toLowerCase() === 'p680'
    && String(progress.runtimeStage || '').trim().toLowerCase() === 'scene_images_generated'
    && String(progress.currentStage?.code || '').trim().toLowerCase() === 'p710'
    && NARRATION_WAITING_SLOT_STATES.has(String(progress.currentStage?.state || '').trim().toLowerCase());
}

export function runFailureMessage(progress: RunStatusProjection | null | undefined): string {
  const message = String(progress?.failure?.message || '').trim();
  if (message) return message;
  const stage = String(progress?.failure?.stage || '').trim();
  if (stage) return `${stage} で停止しました`;
  return '処理が失敗しました';
}
