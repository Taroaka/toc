import { describe, expect, it } from 'vitest';
import { higgsfieldDurationError, nativeAudioModeAfterProviderSwitch, shouldSendNativeAudioMode, videoInputModeError, videoInputReferences } from './HiggsfieldSettings';

describe('Higgsfield request settings', () => {
  it('uses ordered reference images without frame boundaries in reference mode', () => {
    expect(videoInputReferences('higgsfield', 'reference_images', 'start.png', 'end.png', ['ref-a.png', 'ref-b.png']))
      .toEqual({ first_reference: '', last_reference: '', references: ['ref-a.png', 'ref-b.png'] });
  });

  it('sends only start and optional end frames in frame mode', () => {
    expect(videoInputReferences('higgsfield', 'image_to_video', 'start.png', 'end.png', ['ignored.png']))
      .toEqual({ first_reference: 'start.png', last_reference: 'end.png', references: [] });
  });

  it('keeps existing reference behavior for other providers', () => {
    expect(videoInputReferences('seedance', 'image_to_video', 'start.png', null, ['reference.png']))
      .toEqual({ first_reference: 'start.png', last_reference: '', references: ['reference.png'] });
  });

  it('accepts Higgsfield durations from 4 through 30 seconds without coercing other values', () => {
    expect(higgsfieldDurationError(4)).toBeNull();
    expect(higgsfieldDurationError(30)).toBeNull();
    expect(higgsfieldDurationError(3)).toContain('4〜30');
    expect(higgsfieldDurationError(31)).toContain('4〜30');
  });

  it('turns generated audio off on a provider switch and transmits off only when the audio setting changed', () => {
    const mode = nativeAudioModeAfterProviderSwitch('kling_3_0', 'natural_sound');
    expect(mode).toBe('off');
    expect(shouldSendNativeAudioMode('kling_3_0', true)).toBe(true);
    expect(shouldSendNativeAudioMode('kling_3_0', false)).toBe(false);
    expect(shouldSendNativeAudioMode('higgsfield', false)).toBe(true);
  });

  it('requires a start frame or at least one ordered reference for the selected Higgsfield mode', () => {
    expect(videoInputModeError('higgsfield', 'image_to_video', null, [])).toContain('開始フレーム');
    expect(videoInputModeError('higgsfield', 'reference_images', null, [])).toContain('1枚以上');
    expect(videoInputModeError('higgsfield', 'reference_images', null, ['ref.png'])).toBeNull();
    expect(videoInputModeError('seedance', 'image_to_video', null, [])).toBeNull();
  });
});
