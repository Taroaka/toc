import { describe, expect, it } from 'vitest';
import { mixKey, readAudioMix, validMix } from './audioMix';

describe('audio mixer drafts', () => {
  it('preserves old sound plans with unity gain and independent channels', () => {
    const first = readAudioMix();
    first.se.volume_db = 24;
    expect(first.narration.volume_db).toBe(0);
    expect(readAudioMix().se.volume_db).toBe(0);
    expect(validMix(first)).toBe(true);
  });
  it('tracks mute independently without losing the saved gain', () => {
    const a = readAudioMix({ bgm: { volume_db: -12, muted: true } });
    const b = readAudioMix(a);
    b.bgm.muted = false;
    expect(mixKey(a)).not.toBe(mixKey(b));
    expect(b.bgm.volume_db).toBe(-12);
  });
  it('rejects non-finite and out of range values', () => {
    for (const gain of [NaN, Infinity, 37, -61]) {
      const mix = readAudioMix();
      mix.se.volume_db = gain;
      expect(validMix(mix)).toBe(false);
    }
  });
});
