export type VideoInputMode = 'image_to_video' | 'reference_images';
export type VideoNativeAudioMode = 'off' | 'natural_sound' | 'dialogue_and_sound';

export function higgsfieldDurationError(durationSeconds: number): string | null {
  if (!Number.isFinite(durationSeconds) || durationSeconds < 4 || durationSeconds > 30) {
    return 'Higgsfield / Seedance 2.5 の動画は4〜30秒で指定してください。';
  }
  return null;
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
