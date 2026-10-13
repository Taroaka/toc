import { describe, expect, it } from 'vitest';
import { higgsfieldDurationError, KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL, nativeAudioModeAfterProviderSwitch, shouldSendNativeAudioMode, videoDurationBounds, videoDurationError, videoInputModeError, videoInputReferences, usesModelDefaultVideoQuality } from './HiggsfieldSettings';

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

  it('uses Kling v3 standard duration and quality behavior from the selected model ID', () => {
    expect(videoDurationBounds('higgsfield', KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL)).toEqual({
      min: 3,
      max: 15,
      label: 'Kling v3 standard · 3〜15秒',
    });
    expect(videoDurationError(3, 'higgsfield', KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL)).toBeNull();
    expect(videoDurationError(15, 'higgsfield', KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL)).toBeNull();
    expect(videoDurationError(2, 'higgsfield', KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL)).toContain('3〜15');
    expect(videoDurationError(16, 'higgsfield', KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL)).toContain('3〜15');
    expect(usesModelDefaultVideoQuality(KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL)).toBe(true);
  });

  it('keeps Seedance 2.5 image and reference models at 4 through 30 seconds', () => {
    for (const model of [
      'bytedance/seedance-2.5/image-to-video',
      'bytedance/seedance-2.5/reference-to-video',
    ]) {
      expect(videoDurationBounds('higgsfield', model)).toEqual({
        min: 4,
        max: 30,
        label: 'Seedance 2.5 · 4〜30秒',
      });
      expect(videoDurationError(4, 'higgsfield', model)).toBeNull();
      expect(videoDurationError(30, 'higgsfield', model)).toBeNull();
      expect(videoDurationError(3, 'higgsfield', model)).toContain('4〜30');
      expect(videoDurationError(31, 'higgsfield', model)).toContain('4〜30');
      expect(usesModelDefaultVideoQuality(model)).toBe(false);
    }
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
