import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('react-dom/client', () => ({ createRoot: () => ({ render: () => undefined }) }));

let buildCreateRunRequest: typeof import('./main').buildCreateRunRequest;
let cinematicDirectionEntries: typeof import('./main').cinematicDirectionEntries;

beforeAll(async () => {
  vi.stubGlobal('document', {
    getElementById: () => ({}),
    querySelector: (selector: string) => selector === 'head' ? { prepend: () => undefined } : null,
    createElement: () => ({ setAttribute: () => undefined }),
  });
  const main = await import('./main');
  buildCreateRunRequest = main.buildCreateRunRequest;
  cinematicDirectionEntries = main.cinematicDirectionEntries;
});

afterAll(() => vi.unstubAllGlobals());

describe('new-run filming preferences', () => {
  const values = { title: '  作品  ', source: ' source ', cinematicPreferences: '  色と光  ',
    targetDurationSeconds: 600, sourceRunId: 'source-run' };

  it('sends trimmed filming preferences for normal and storyboard runs', () => {
    const normal = buildCreateRunRequest('normal', values);
    const storyboard = buildCreateRunRequest('scene_storyboard', values);
    expect(normal.endpoint).toBe('/api/image-gen/runs/create');
    expect(storyboard.endpoint).toBe('/api/image-gen/runs/create/storyboard');
    expect(normal.body.cinematic_preferences).toBe('色と光');
    expect(storyboard.body.cinematic_preferences).toBe('色と光');
  });

  it('sends null for a blank preference and omits it for world walk', () => {
    expect(buildCreateRunRequest('normal', { ...values, cinematicPreferences: '  ' }).body.cinematic_preferences).toBeNull();
    expect(buildCreateRunRequest('world_walk', values).body).not.toHaveProperty('cinematic_preferences');
  });
});

describe('effective filming direction display', () => {
  it('shows readable direction fields while omitting origins and raw identifiers', () => {
    const entries = cinematicDirectionEntries({
      film_language: {
        fields: { palette: '青と琥珀', exposure: '白飛びを抑える', texture: '粒子のある質感', camera: 'ゆるやかな寄り', source_id: 'source-123', sha256: 'sha256:abc' },
        origins: { palette: 'source-123', request_hash: 'sha256:abc' },
      },
      light_continuity: '窓からの斜光を保つ',
      focus: { initial: '手前の表情', change: 'ゆっくり背景へ移す', target_id: 'cut-1' },
      performance: { action: '振り返る', observable_reaction: '視線が止まる', timing: '短く間を置く' },
      physics: '接触後に物がわずかに揺れる',
    });
    expect(entries.map((entry) => entry.label)).toContain('色と配色');
    expect(entries.map((entry) => entry.label)).toContain('露出');
    expect(entries.map((entry) => entry.label)).toContain('質感');
    expect(entries.map((entry) => entry.label)).toContain('カメラ');
    expect(entries.map((entry) => entry.label)).toContain('照明の継続');
    expect(entries.map((entry) => entry.label)).toContain('ピント');
    expect(entries.find((entry) => entry.label === 'ピント')?.value).toContain('初期のピント：手前の表情');
    expect(entries.find((entry) => entry.label === '演技と動作')?.value).toContain('目に見える反応：視線が止まる');
    expect(JSON.stringify(entries)).not.toContain('source-123');
    expect(JSON.stringify(entries)).not.toContain('sha256:abc');
    expect(JSON.stringify(entries)).not.toContain('target_id');
  });
});
