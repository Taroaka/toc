export const MIX_CHANNELS = ['narration', 'se', 'bgm'] as const;
export type MixChannelName = typeof MIX_CHANNELS[number];
export type ChannelGain = { volume_db: number; muted: boolean };
export type AudioMix = Record<MixChannelName, ChannelGain>;

export function readAudioMix(value?: Partial<AudioMix> | null): AudioMix {
  return Object.fromEntries(MIX_CHANNELS.map(name => [name, {
    volume_db: value?.[name]?.volume_db ?? 0,
    muted: value?.[name]?.muted ?? false,
  }])) as AudioMix;
}

export function mixKey(value: AudioMix): string {
  return JSON.stringify(MIX_CHANNELS.map(name => [value[name].volume_db, value[name].muted]));
}

export function validMix(value: AudioMix): boolean {
  return MIX_CHANNELS.every(name => Number.isFinite(value[name].volume_db)
    && value[name].volume_db >= -60 && value[name].volume_db <= 36);
}
