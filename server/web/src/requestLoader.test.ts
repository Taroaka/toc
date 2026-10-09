import { describe, expect, it, vi } from 'vitest';
import { shareRequest } from './requestLoader';

describe('shareRequest', () => {
  it('shares the same in-flight promise for a scope and allows a later refresh', async () => {
    const inFlight = new Map<string, Promise<string>>();
    let resolve!: (value: string) => void;
    const request = vi.fn()
      .mockImplementationOnce(() => new Promise<string>((done) => { resolve = done; }))
      .mockResolvedValue('refreshed');

    const first = shareRequest(inFlight, 'run:scene:narration', request);
    const second = shareRequest(inFlight, 'run:scene:narration', request);
    expect(second).toBe(first);
    expect(request).toHaveBeenCalledOnce();

    resolve('loaded');
    await expect(first).resolves.toBe('loaded');
    await expect(shareRequest(inFlight, 'run:scene:narration', request)).resolves.toBe('refreshed');
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('cleans up rejected requests so a retry is possible', async () => {
    const inFlight = new Map<string, Promise<string>>();
    const request = vi.fn()
      .mockRejectedValueOnce(new Error('narration unavailable'))
      .mockResolvedValueOnce('retry');

    await expect(shareRequest(inFlight, 'run:scene:narration', request)).rejects.toThrow('narration unavailable');
    await expect(shareRequest(inFlight, 'run:scene:narration', request)).resolves.toBe('retry');
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('lets an A to B to A scope transition commit the shared A result for both A callers', async () => {
    const inFlight = new Map<string, Promise<string>>();
    let resolveA!: (value: string) => void;
    let resolveB!: (value: string) => void;
    const request = vi.fn((key: string) => new Promise<string>((resolve) => {
      if (key === 'A') resolveA = resolve;
      else resolveB = resolve;
    }));
    let aCommits = 0;
    let bCommits = 0;

    const a1 = shareRequest(inFlight, 'A', () => request('A')).then(() => { aCommits += 1; });
    const b = shareRequest(inFlight, 'B', () => request('B')).then(() => { bCommits += 1; });
    const a2 = shareRequest(inFlight, 'A', () => request('A')).then(() => { aCommits += 1; });
    expect(request).toHaveBeenCalledTimes(2);

    resolveA('A loaded');
    resolveB('B loaded');
    await Promise.all([a1, b, a2]);
    expect(aCommits).toBe(2);
    expect(bCommits).toBe(1);
  });
});
