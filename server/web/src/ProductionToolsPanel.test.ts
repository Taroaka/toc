import { describe, expect, it } from 'vitest';
import { canAdoptVideo, normalizeRegions, normalizeVideoSettings, validateRegionSelection, sameProductionContextIdentity, type VideoEditSettings } from './ProductionToolsPanel';

describe('production tool input helpers', () => {
  it('rejects manually entered invalid regions instead of silently changing the preserved area', () => {
    const region = { x: .2, y: .2, width: .3, height: .4 };
    expect(validateRegionSelection([region])).toEqual([region]);
    expect(() => validateRegionSelection([{ ...region, width: 2 }])).toThrow('画像の内側');
    expect(() => validateRegionSelection([{ ...region, x: NaN }])).toThrow('画像の内側');
    expect(() => validateRegionSelection([])).toThrow('画像の内側');
  });
  it('does not accept an async response for a different run, item, or media kind', () => {
    const captured = { runId: 'run-a', itemId: 'scene1_cut1', kind: 'video' as const };
    expect(sameProductionContextIdentity(captured, { ...captured })).toBe(true);
    expect(sameProductionContextIdentity(captured, { ...captured, runId: 'run-b' })).toBe(false);
    expect(sameProductionContextIdentity(captured, { ...captured, itemId: 'scene1_cut2' })).toBe(false);
    expect(sameProductionContextIdentity(captured, { ...captured, kind: 'image' })).toBe(false);
  });

  it('clamps normalized rectangles to the image and removes empty regions', () => {
    const result = normalizeRegions([
      { x: -0.2, y: 0.25, width: 0.7, height: 1 },
      { x: 0.5, y: 0.5, width: 0, height: 0.2 },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].x).toBe(0);
    expect(result[0].y).toBe(0.25);
    expect(result[0].width).toBeCloseTo(0.5);
    expect(result[0].height).toBe(0.75);
  });

  it('accepts bounded color and trim settings and rejects ranges outside source media', () => {
    const settings: VideoEditSettings = { start_seconds: 1, duration_seconds: 8, brightness: 0.2, contrast: 1.5,
      saturation: 0.5, gamma: 1.2, fade_in_seconds: 1, fade_out_seconds: 2 };
    expect(normalizeVideoSettings(settings, 10)).toEqual(settings);
    expect(() => normalizeVideoSettings({ ...settings, start_seconds: 3 }, 10)).toThrow('元動画の範囲');
    expect(() => normalizeVideoSettings({ ...settings, brightness: 0.3 }, 10)).toThrow('明るさ');
    expect(() => normalizeVideoSettings({ ...settings, fade_in_seconds: 9 }, 10)).toThrow('フェード時間');
  });

  it('allows adoption only when the edit covers the planned cut within the duration tolerance', () => {
    expect(canAdoptVideo(12, 12)).toBe(true);
    expect(canAdoptVideo(11.96, 12)).toBe(true);
    expect(canAdoptVideo(11.9, 12)).toBe(false);
    expect(canAdoptVideo(2, 0)).toBe(false);
  });
});
