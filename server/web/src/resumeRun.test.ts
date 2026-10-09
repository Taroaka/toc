import { describe, expect, it, vi } from 'vitest';
import { resumeRun } from './resumeRun';

describe('resumeRun', () => {
  it('resumes the same run and waits for completion without submitting a new source', async () => {
    const fetchJson = vi.fn()
      .mockResolvedValueOnce({ jobId: 'job', status: 'running', message: '再開中' })
      .mockResolvedValueOnce({ jobId: 'job', status: 'completed' });
    const onMessage = vi.fn();
    const result = await resumeRun('物語 run', { fetchJson, sleep: async () => {}, onMessage });
    expect(fetchJson.mock.calls[0][0]).toBe('/api/image-gen/runs/' + encodeURIComponent('物語 run') + '/resume');
    expect(JSON.parse(fetchJson.mock.calls[0][1].body)).toEqual({ stop_target: 'p680' });
    expect(fetchJson.mock.calls[1][0]).toBe('/api/image-gen/runs/create/job');
    expect(onMessage).toHaveBeenCalledWith('再開中');
    expect(result.status).toBe('completed');
  });

  it('surfaces the job failure and does not automatically start another retry', async () => {
    const fetchJson = vi.fn().mockResolvedValue({ jobId: 'job', status: 'failed', error: '入力が変更されています' });
    await expect(resumeRun('run', { fetchJson, sleep: async () => {}, onMessage: vi.fn() }))
      .rejects.toThrow('入力が変更されています');
    expect(fetchJson).toHaveBeenCalledOnce();
  });

  it('adds continue_waiting only when starting narration from p680', async () => {
    const fetchJson = vi.fn()
      .mockResolvedValueOnce({ jobId: 'job', status: 'running', message: 'ナレーション待機を開始中' })
      .mockResolvedValueOnce({ jobId: 'job', status: 'completed' });

    await resumeRun('run', {
      fetchJson,
      sleep: async () => {},
      onMessage: vi.fn(),
      continueWaiting: true,
    });

    expect(JSON.parse(fetchJson.mock.calls[0][1].body)).toEqual({
      stop_target: 'p680',
      continue_waiting: true,
    });
  });

  it('keeps the legacy resume payload when continueWaiting is omitted', async () => {
    const fetchJson = vi.fn()
      .mockResolvedValueOnce({ jobId: 'job', status: 'running' })
      .mockResolvedValueOnce({ jobId: 'job', status: 'completed' });

    await resumeRun('run', { fetchJson, sleep: async () => {}, onMessage: vi.fn() });

    expect(JSON.parse(fetchJson.mock.calls[0][1].body)).toEqual({ stop_target: 'p680' });
  });
});
