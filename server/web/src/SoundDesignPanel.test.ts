import { describe, expect, it } from 'vitest';
import { cueMetadata, validCueMetadata, soundRequestChanged, soundSettings, type CueSettings } from './SoundDesignPanel';

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

describe('sound design metadata', () => {
  it('reads legacy cues without inventing an artistic intent', () => {
    const value = cueMetadata({ label: '旧音源' });
    expect(value.source_selector).toBe('full_run');
    expect(value.purpose).toBe('');
    expect(validCueMetadata(value)).toBe(false);
  });
  it('keeps human authored purpose and timing separate from the provider settings', () => {
    const value = cueMetadata({ label:'足音', source_selector:'scene1_cut1', purpose:'近づく存在', perspective:'画面外', timing_reason:'扉が開く前' });
    expect(validCueMetadata(value)).toBe(true);
    expect(soundSettings({ ...saved, ...value })).not.toHaveProperty('purpose');
  });
});
