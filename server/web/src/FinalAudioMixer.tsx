import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, FormControlLabel, LinearProgress, Slider, Stack, Switch, TextField, Typography } from '@mui/material';
import type { SoundStatus } from './SoundDesignPanel';
import { MIX_CHANNELS, mixKey, readAudioMix, validMix, type AudioMix, type ChannelGain, type MixChannelName } from './audioMix';

type MixerStatus = SoundStatus & { plan: (NonNullable<SoundStatus['plan']> & { mix?: AudioMix }) | null };
type Audition = { path: string; settings: AudioMix; video_set_hash: string };
type Props = {
  runId: string;
  disabled: boolean;
  jsonFetch: <T>(input: RequestInfo, init?: RequestInit) => Promise<T>;
  videoFileUrl: (runId: string, path: string) => string;
  onDirty: (value: boolean) => void;
  onBusy: (value: boolean) => void;
  onReady: (value: boolean) => void;
};
const LABELS: Record<MixChannelName, string> = { narration: 'ナレーション', se: 'SE', bgm: 'BGM' };

export function FinalAudioMixer({ runId, disabled, jsonFetch, videoFileUrl, onDirty, onBusy, onReady }: Props) {
  const [data, setData] = useState<MixerStatus | null>(null);
  const [draft, setDraft] = useState<AudioMix>(() => readAudioMix());
  const [preview, setPreview] = useState<Audition | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const player = useRef<HTMLVideoElement | null>(null);
  const saved = readAudioMix(data?.plan?.mix);
  const dirty = Boolean(data) && mixKey(draft) !== mixKey(saved);
  const previewCurrent = preview && mixKey(preview.settings) === mixKey(draft)
    && preview.video_set_hash === data?.context.video_set_hash;
  const apply = useCallback((value: MixerStatus) => {
    if (!mounted.current) return;
    setData(value); setDraft(readAudioMix(value.plan?.mix)); onReady(value.ready);
  }, [onReady]);
  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    if (runId) {
      setBusy('音量設定を読み込み中'); onBusy(true);
      void jsonFetch<MixerStatus>(`/api/image-gen/sound-design?run_id=${encodeURIComponent(runId)}`, { signal: controller.signal })
        .then(apply).catch(e => { if (!controller.signal.aborted) setError(String(e)); })
        .finally(() => { if (!controller.signal.aborted) { setBusy(''); onBusy(false); } });
    }
    return () => { mounted.current = false; controller.abort(); onDirty(false); onBusy(false); };
  }, [runId, jsonFetch, apply, onDirty, onBusy]);
  const act = async (label: string, work: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(label); setError(''); onBusy(true);
    player.current?.pause();
    try { await work(); } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { inFlight.current = false; if (mounted.current) { setBusy(''); onBusy(false); } }
  };
  const post = <T,>(action: string) => jsonFetch<T>(`/api/image-gen/sound-design/${action}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      run_id: runId, revision: data?.plan?.revision ?? 0,
      video_set_hash: data?.context.video_set_hash, settings: draft,
    }),
  });
  const patch = (name: MixChannelName, value: Partial<ChannelGain>) => {
    player.current?.pause();
    setDraft(current => ({ ...current, [name]: { ...current[name], ...value } }));
  };
  const locked = disabled || Boolean(busy) || !data?.ready;
  return <Box component="section" aria-label="最終音量ミキサー" sx={{ gridColumn: '1 / -1', border: '1px solid', borderColor: 'divider', borderRadius: 3, p: { xs: 2, md: 3 } }}>
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
        <Typography variant="h6">音量を調整して試聴</Typography>
        {dirty && <Chip label="音量設定が未保存" color="warning" size="small" />}
      </Stack>
      <Typography variant="body2" color="text.secondary">0 dBは基準音量、＋は増幅、−は減衰です。音源の再生成は不要です。SEには採用した元動画の音声も含みます。</Typography>
      {!data?.ready && !busy && <Alert severity="info">{data?.blockedReason || 'BGM・SE画面で使用する音を確定すると、最終音量を調整できます。'}</Alert>}
      {busy && <><LinearProgress aria-label={busy} /><Typography role="status" variant="body2">{busy}</Typography></>}
      {error && <Alert severity="error">{error}</Alert>}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 3 }}>
        {MIX_CHANNELS.map(name => <Stack key={name} spacing={1}>
          <Typography fontWeight={800}>{LABELS[name]}</Typography>
          <Box sx={{ px: 1, pb: 2 }}><Slider aria-label={`${LABELS[name]}の音量`} min={-60} max={36} step={1} value={draft[name].volume_db}
            disabled={locked || draft[name].muted} valueLabelDisplay="auto" valueLabelFormat={value => `${value > 0 ? '+' : ''}${value} dB`}
            marks={[{ value: -60, label: '−60' }, { value: 0, label: '0' }, { value: 36, label: '+36' }]}
            onChange={(_, value) => patch(name, { volume_db: value as number })} /></Box>
          <Stack direction="row" alignItems="center" gap={1}>
            <TextField label={`${LABELS[name]}（dB）`} size="small" type="number" value={draft[name].volume_db}
              disabled={locked || draft[name].muted} slotProps={{ htmlInput: { min: -60, max: 36, step: 1 } }}
              onChange={event => { const value = Number(event.target.value); if (Number.isFinite(value)) patch(name, { volume_db: Math.min(36, Math.max(-60, value)) }); }} />
            <FormControlLabel label="ミュート" control={<Switch checked={draft[name].muted} disabled={locked}
              inputProps={{ 'aria-label': `${LABELS[name]}をミュート` }} onChange={(_, muted) => patch(name, { muted })} />} />
          </Stack>
        </Stack>)}
      </Box>
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Button variant="contained" disabled={locked || !validMix(draft)} onClick={() => void act('試聴用動画を作成中（生成課金なし）', async () => {
          const value = await post<Audition>('mix-preview');
          if (mounted.current) setPreview(value);
        })}>この音量で試聴</Button>
        <Button variant="outlined" disabled={locked || !dirty || !validMix(draft)} onClick={() => void act('音量設定を保存中', async () => apply(await post<MixerStatus>('mix')))}>音量を保存して書き出しに使用</Button>
        <Button disabled={locked} onClick={() => { player.current?.pause(); setDraft(readAudioMix()); }}>3つとも0 dBに戻す</Button>
        <Button disabled={disabled || Boolean(busy) || !runId} onClick={() => void act('保存値を読み込み中', async () => {
          const value = await jsonFetch<MixerStatus>(`/api/image-gen/sound-design?run_id=${encodeURIComponent(runId)}`);
          if (mounted.current) { setPreview(null); apply(value); }
        })}>最新の保存値を読み込む</Button>
      </Stack>
      <Typography variant="caption" color="text.secondary">スライダーを変えたら「この音量で試聴」で再作成してください。試聴と書き出しは同じ音声処理を使います。個別素材の音量に加算し、最後に音割れ防止を適用します。</Typography>
      {preview && !previewCurrent && <Alert severity="warning">音量が変わりました。「この音量で試聴」でプレビューを更新してください。</Alert>}
      {preview && <video ref={player} key={preview.path} controls={Boolean(previewCurrent)} preload="metadata"
        src={videoFileUrl(runId, preview.path)} aria-label="音量調整プレビュー"
        style={{ width: '100%', maxHeight: 520, borderRadius: 12 }} />}
      {dirty && <Alert severity="info">試聴は未保存の音量でもできます。最終書き出しの前に音量設定を保存してください。</Alert>}
    </Stack>
  </Box>;
}
