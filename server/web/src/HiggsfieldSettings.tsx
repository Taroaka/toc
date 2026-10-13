export type VideoInputMode = 'image_to_video' | 'reference_images';
export type VideoNativeAudioMode = 'off' | 'natural_sound' | 'dialogue_and_sound';

export const KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL = 'kling-video/v3.0/std/image-to-video';

const SEEDANCE_25_MODELS = new Set([
  'bytedance/seedance-2.5/image-to-video',
  'bytedance/seedance-2.5/reference-to-video',
]);

export type VideoDurationBounds = {
  min: number;
  max: number;
  label: string;
};

export function usesModelDefaultVideoQuality(model?: string | null): boolean {
  return (model || '').trim() === KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL;
}

export function videoDurationBounds(tool: string, model?: string | null): VideoDurationBounds | null {
  const selectedModel = (model || '').trim();
  if (selectedModel === KLING_V3_STANDARD_IMAGE_TO_VIDEO_MODEL) {
    return { min: 3, max: 15, label: 'Kling v3 standard · 3〜15秒' };
  }
  if (SEEDANCE_25_MODELS.has(selectedModel) || (tool === 'higgsfield' && !selectedModel)) {
    return { min: 4, max: 30, label: 'Seedance 2.5 · 4〜30秒' };
  }
  return null;
}

export function videoDurationError(durationSeconds: number, tool: string, model?: string | null): string | null {
  const bounds = videoDurationBounds(tool, model);
  if (!bounds) return null;
  if (!Number.isFinite(durationSeconds) || durationSeconds < bounds.min || durationSeconds > bounds.max) {
    return `${bounds.label}で指定してください。`;
  }
  return null;
}

export function higgsfieldDurationError(durationSeconds: number): string | null {
  return videoDurationError(durationSeconds, 'higgsfield');
}

export function nativeAudioModeAfterProviderSwitch(
  tool: string,
  mode: VideoNativeAudioMode,
): VideoNativeAudioMode {
  return tool === 'higgsfield' ? mode : 'off';
}

export function shouldSendNativeAudioMode(tool: string, explicitlyDirty: boolean): boolean {
  return tool === 'higgsfield' || explicitlyDirty;
}

export function videoInputModeError(
  tool: string,
  mode: VideoInputMode,
  firstReference: string | null,
  references: string[],
): string | null {
  if (tool !== 'higgsfield') return null;
  if (mode === 'image_to_video' && !firstReference) return '開始フレーム画像を選択してください。';
  if (mode === 'reference_images' && references.length === 0) return '参照画像を1枚以上選択してください。';
  return null;
}

export function videoInputReferences(
  tool: string,
  mode: VideoInputMode,
  firstReference: string | null,
  lastReference: string | null,
  references: string[],
) {
  if (tool === 'higgsfield') {
    return mode === 'reference_images'
      ? { first_reference: '', last_reference: '', references }
      : { first_reference: firstReference || '', last_reference: lastReference || '', references: [] as string[] };
  }
  return {
    first_reference: mode === 'reference_images' ? '' : firstReference,
    last_reference: lastReference || '',
    references,
  };
}
