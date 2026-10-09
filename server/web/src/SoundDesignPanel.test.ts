import { describe, expect, it } from 'vitest';
import { soundRequestChanged, soundSettings, type CueSettings } from './SoundDesignPanel';

const saved: CueSettings = { prompt: '静かな音楽', generation_duration_seconds: 30, start_seconds: 0,
  duration_seconds: 120, volume_db: -20, fade_in_seconds: 1, fade_out_seconds: 2,
  loop: true, enabled: false, selected_candidate_id: null };

describe('sound cue draft boundaries', () => {
  it('preserves unsaved mix drafts when candidates/provenance refresh', () => {
    const refreshed = { ...saved, candidates: [{ id: 'new' }], current_request_hash: 'new' };
    expect(soundSettings(refreshed)).toEqual(soundSettings(saved));
    expect(soundSettings(refreshed)).not.toHaveProperty('candidates');
  });
  it('mix timing and volume do not require paying for new generated audio', () => {
    expect(soundRequestChanged({ ...saved, start_seconds: 2, volume_db: -15 }, saved, 'bgm')).toBe(false);
    expect(soundRequestChanged({ ...saved, loop: false }, saved, 'bgm')).toBe(false);
  });
  it('prompt, generation duration and SE loop changes prevent adopting older candidates', () => {
    expect(soundRequestChanged({ ...saved, prompt: '別の音' }, saved, 'bgm')).toBe(true);
    expect(soundRequestChanged({ ...saved, generation_duration_seconds: 60 }, saved, 'bgm')).toBe(true);
    expect(soundRequestChanged({ ...saved, loop: false }, saved, 'se')).toBe(true);
  });
});
