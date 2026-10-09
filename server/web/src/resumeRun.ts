import { pollCreateRun, type CreateRunPollingStatus } from './createRunPolling';

type ResumeJob = CreateRunPollingStatus & { jobId: string; error?: string | null };
type ResumeOptions = {
  fetchJson: (url: string, init?: RequestInit) => Promise<ResumeJob>;
  sleep: () => Promise<void>;
  onMessage: (message: string) => void;
  continueWaiting?: boolean;
};

export async function resumeRun(runId: string, options: ResumeOptions): Promise<ResumeJob> {
  const started = await options.fetchJson(`/api/image-gen/runs/${encodeURIComponent(runId)}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      stop_target: 'p680',
      ...(options.continueWaiting ? { continue_waiting: true } : {}),
    }),
  });
  if (started.message) options.onMessage(started.message);
  const latest = await pollCreateRun(started, {
    ...options,
    fetchStatus: () => options.fetchJson(`/api/image-gen/runs/create/${encodeURIComponent(started.jobId)}`),
  });
  if (latest.status === 'failed') throw new Error(latest.error || '再開した処理が失敗しました');
  return latest;
}
