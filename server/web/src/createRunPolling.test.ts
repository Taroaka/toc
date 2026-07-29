import { describe, expect, it, vi } from 'vitest';

import {
  pollCreateRun,
  type CreateRunPollingStatus,
} from './createRunPolling';

function status(
  value: CreateRunPollingStatus['status'],
  message?: string,
): CreateRunPollingStatus {
  return { status: value, message };
}

describe('pollCreateRun', () => {
  it('keeps polling past 30 running updates until the run completes', async () => {
    const updates = [
      ...Array.from({ length: 31 }, () => status('running')),
      status('completed', '作成完了'),
    ];
    const fetchStatus = vi.fn(async () => {
      const update = updates.shift();
      if (!update) throw new Error('unexpected extra poll');
      return update;
    });
    const sleep = vi.fn(async () => undefined);

    const result = await pollCreateRun(status('running'), {
      fetchStatus,
      sleep,
      onMessage: vi.fn(),
    });

    expect(result).toEqual(status('completed', '作成完了'));
    expect(fetchStatus).toHaveBeenCalledTimes(32);
    expect(sleep).toHaveBeenCalledTimes(32);
  });

  it.each(['completed', 'paused', 'failed'] as const)(
    'stops and returns a %s terminal update',
    async (terminalStatus) => {
      const terminal = status(terminalStatus);
      const fetchStatus = vi.fn(async () => terminal);
      const sleep = vi.fn(async () => undefined);

      const result = await pollCreateRun(status('running'), {
        fetchStatus,
        sleep,
        onMessage: vi.fn(),
      });

      expect(result).toBe(terminal);
      expect(fetchStatus).toHaveBeenCalledOnce();
      expect(sleep).toHaveBeenCalledOnce();
    },
  );

  it('reports each non-empty status message to the caller', async () => {
    const updates = [
      status('running', '調査中'),
      status('running'),
      status('paused', '承認待ち'),
    ];
    const fetchStatus = vi.fn(async () => {
      const update = updates.shift();
      if (!update) throw new Error('unexpected extra poll');
      return update;
    });
    const onMessage = vi.fn();

    await pollCreateRun(status('running'), {
      fetchStatus,
      sleep: async () => undefined,
      onMessage,
    });

    expect(onMessage.mock.calls).toEqual([['調査中'], ['承認待ち']]);
  });
});
