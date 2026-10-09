import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Checkbox, Chip, FormControlLabel, LinearProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';

type Candidate = { id: string; status: string; path: string | null; error?: string; duration_seconds?: number; request_hash: string };
export type CueSettings = {
  prompt: string; generation_duration_seconds: number; start_seconds: number; duration_seconds: number;
  volume_db: number; fade_in_seconds: number; fade_out_seconds: number; loop: boolean;
  enabled: boolean; selected_candidate_id: string | null;
};
export type CueMetadata = { label: string; source_selector: string; purpose: string; perspective: string; timing_reason: string };
type Cue = CueSettings & Partial<CueMetadata> & { id: string; kind: 'bgm' | 'se'; label: string; candidates: Candidate[]; current_request_hash: string };
export function cueMetadata(cue: Partial<CueMetadata>): CueMetadata {
  return { label: cue.label || '', source_selector: cue.source_selector || 'full_run', purpose: cue.purpose || '',
    perspective: cue.perspective || '', timing_reason: cue.timing_reason || '' };
}
export function validCueMetadata(value: CueMetadata) { return Object.values(value).every(v => v.trim().length > 0); }

export type NativeAudioSettings = { enabled: boolean; volume_db: number; fade_in_seconds: number; fade_out_seconds: number; overlap_policy: 'preserve' | 'duck_narration' };
type NativeTrack = NativeAudioSettings & { item_id: string; mode: 'off' | 'natural_sound' | 'dialogue_and_sound'; available: boolean; path: string; start_seconds: number; duration_seconds: number };
export function soundSettings(cue: CueSettings): CueSettings {
  return { prompt: cue.prompt, generation_duration_seconds: cue.generation_duration_seconds,
    start_seconds: cue.start_seconds, duration_seconds: cue.duration_seconds, volume_db: cue.volume_db,
    fade_in_seconds: cue.fade_in_seconds, fade_out_seconds: cue.fade_out_seconds,
    loop: cue.loop, enabled: cue.enabled, selected_candidate_id: cue.selected_candidate_id };
}
export function soundRequestChanged(draft: CueSettings, saved: CueSettings, kind: 'bgm' | 'se') {
  return draft.prompt !== saved.prompt || draft.generation_duration_seconds !== saved.generation_duration_seconds
    || (kind === 'se' && draft.loop !== saved.loop);
}
export type SoundStatus = {
  runId: string; approved: boolean; ready: boolean; blockedReason: string;
  context: { video_set_hash: string; duration_seconds: number; videos: { item_id: string; path: string; duration_seconds: number; start_seconds: number; native_audio_mode?: string }[] };
  plan: { revision: number; status: string; cues: Cue[]; native_tracks?: NativeTrack[]; designs?: { id: string; intent: string; silence_regions: { start_seconds: number; duration_seconds: number; reason: string; mode: string }[] }[] } | null;
};
type Props = {
  runId: string;
  jsonFetch: <T>(input: RequestInfo, init?: RequestInit) => Promise<T>;
  audioFileUrl: (runId: string, path: string) => string;
  videoFileUrl: (runId: string, path: string) => string;
  onReady: (value: boolean) => void;
  onBusy: (value: boolean) => void;
};

function SoundCueCard({ cue, disabled, url, onSave, onGenerate, onDirty, onDelete, targets }: {
  cue: Cue; disabled: boolean; url: (path: string) => string;
  onSave: (cue: CueSettings, metadata?: CueMetadata) => Promise<void>; onGenerate: (cue: CueSettings, metadata?: CueMetadata) => Promise<void>;
  onDelete: () => Promise<void>; targets: { item_id: string }[];
  onDirty: (id: string, value: boolean) => void;
}) {
  const [draft, setDraft] = useState<CueSettings>(() => soundSettings(cue));
  const savedSettings = JSON.stringify(soundSettings(cue));
  useEffect(() => setDraft(JSON.parse(savedSettings) as CueSettings), [savedSettings]);
  const savedMetadata = JSON.stringify(cueMetadata(cue));
  const [metadata, setMetadata] = useState<CueMetadata>(() => cueMetadata(cue));
  useEffect(() => setMetadata(JSON.parse(savedMetadata) as CueMetadata), [savedMetadata]);
  const metadataDirty = JSON.stringify(metadata) !== savedMetadata;
  const metadataInvalid = metadataDirty && !validCueMetadata(metadata);
  const dirty = JSON.stringify(soundSettings(draft)) !== savedSettings || metadataDirty;
  useEffect(() => () => onDirty(cue.id, false), [cue.id, onDirty]);
  useEffect(() => { onDirty(cue.id, dirty); }, [cue.id, dirty, onDirty]);
  const patch = (value: Partial<CueSettings>) => setDraft(current => ({ ...current, ...value }));
  const number = (key: keyof CueSettings, label: string, min: number, max: number, step = 0.1) => (
    <TextField key={key} label={label} type="number" size="small" value={draft[key]} disabled={disabled}
      slotProps={{ htmlInput: { min, max, step } }}
      onChange={event => patch({ [key]: Number(event.target.value) })} sx={{ width: 150 }} />
  );
  return <Card variant="outlined" sx={{ minWidth: 0 }}>
    <CardContent>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip label={cue.kind === 'bgm' ? 'BGM' : 'SE'} color={cue.kind === 'bgm' ? 'primary' : 'default'} size="small" />
          <Typography fontWeight={800}>{cue.label}</Typography>
          {cue.enabled && <Chip label="採用中" color="success" size="small" />}
        </Stack>
        <Stack direction="row" useFlexGap flexWrap="wrap" gap={2}>
          <TextField label="音の名前" value={metadata.label} disabled={disabled} onChange={e => setMetadata({ ...metadata, label: e.target.value })} />
          <TextField select label="対象" value={metadata.source_selector} disabled={disabled} sx={{ minWidth: 180 }} onChange={e => setMetadata({ ...metadata, source_selector: e.target.value })}>
            <MenuItem value="full_run">全編</MenuItem>{targets.map(t => <MenuItem key={t.item_id} value={t.item_id}>{t.item_id}</MenuItem>)}
          </TextField>
        </Stack>
        <TextField label="狙う効果・必要な理由" value={metadata.purpose} disabled={disabled} multiline onChange={e => setMetadata({ ...metadata, purpose: e.target.value })} />
        <TextField label="音の視点（劇中音・劇伴・主観音など）" value={metadata.perspective} disabled={disabled} onChange={e => setMetadata({ ...metadata, perspective: e.target.value })} />
        <TextField label="音が入る・終わる理由" value={metadata.timing_reason} disabled={disabled} multiline onChange={e => setMetadata({ ...metadata, timing_reason: e.target.value })} />
        <TextField label="生成指示" multiline minRows={3} value={draft.prompt} disabled={disabled}
          onChange={event => patch({ prompt: event.target.value })} inputProps={{ maxLength: 4100 }} fullWidth />
        <Stack direction="row" useFlexGap flexWrap="wrap" gap={2}>
          {number('generation_duration_seconds', '生成する長さ（秒）', cue.kind === 'bgm' ? 3 : 0.5, cue.kind === 'bgm' ? 600 : 30)}
          {number('start_seconds', '開始位置（秒）', 0, 86400)}
          {number('duration_seconds', '再生する長さ（秒）', 0.1, 86400)}
          {number('volume_db', '音量（dB）', -60, 36, 1)}
          {number('fade_in_seconds', 'フェードイン（秒）', 0, 60)}
          {number('fade_out_seconds', 'フェードアウト（秒）', 0, 60)}
        </Stack>
        <Stack direction="row" useFlexGap flexWrap="wrap" gap={1}>
          <FormControlLabel control={<Checkbox checked={draft.loop} disabled={disabled} onChange={(_, loop) => patch({ loop })} />} label="繰り返す" />
          <FormControlLabel control={<Checkbox checked={draft.enabled} disabled={disabled || !draft.selected_candidate_id} onChange={(_, enabled) => patch({ enabled })} />} label="最終動画に使用" />
          <Button disabled={disabled} color="error" onClick={() => void onDelete()}>この音を削除（音源は履歴に保持）</Button>
          <Button disabled={disabled || metadataInvalid} variant="outlined" onClick={() => void onSave(draft, metadataDirty ? metadata : undefined)}>設定を保存</Button>
          <Button disabled={disabled || metadataInvalid || !draft.prompt.trim()} variant="contained" onClick={() => void onGenerate(draft, metadataDirty ? metadata : undefined)}>保存して音声候補を生成</Button>
        </Stack>
        {!cue.candidates.length && <Typography variant="body2" color="text.secondary">生成後にここで試聴して採用できます。</Typography>}
        {cue.candidates.map((candidate, index) => <Box key={candidate.id} sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
            <Typography variant="body2">候補 {index + 1}{candidate.duration_seconds ? ` · ${candidate.duration_seconds.toFixed(1)}秒` : ''}</Typography>
            {candidate.path && <audio controls preload="none" src={url(candidate.path)} aria-label={`${cue.label} 候補${index + 1}`} />}
            {candidate.status === 'completed' && <Button size="small" disabled={disabled || metadataInvalid || soundRequestChanged(draft, cue, cue.kind) || candidate.request_hash !== cue.current_request_hash}
              onClick={() => void onSave({ ...draft, selected_candidate_id: candidate.id, enabled: true }, metadataDirty ? metadata : undefined)}>
              {candidate.id === cue.selected_candidate_id ? '採用済み' : 'この候補を採用'}
            </Button>}
          </Stack>
          {candidate.error && <Alert severity="error">{candidate.error}</Alert>}
          {candidate.request_hash !== cue.current_request_hash && <Typography variant="caption" color="text.secondary">以前の生成指示の候補です。</Typography>}
        </Box>)}
      </Stack>
    </CardContent>
  </Card>;
}

function NativeAudioCard({ track, disabled, videoUrl, onSave, onDirty }: {
  track: NativeTrack; disabled: boolean; videoUrl: string;
  onSave: (settings: NativeAudioSettings) => Promise<void>; onDirty: (id: string, dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState<NativeAudioSettings>(() => ({ enabled: track.enabled, volume_db: track.volume_db,
    fade_in_seconds: track.fade_in_seconds, fade_out_seconds: track.fade_out_seconds, overlap_policy: track.overlap_policy }));
  const saved = JSON.stringify({ enabled: track.enabled, volume_db: track.volume_db, fade_in_seconds: track.fade_in_seconds,
    fade_out_seconds: track.fade_out_seconds, overlap_policy: track.overlap_policy });
  useEffect(() => setDraft(JSON.parse(saved) as NativeAudioSettings), [saved]);
  const dirty = JSON.stringify(draft) !== saved;
  useEffect(() => { onDirty(`native:${track.item_id}`, dirty); }, [dirty, onDirty, track.item_id]);
  const patch = (value: Partial<NativeAudioSettings>) => setDraft(current => ({ ...current, ...value }));
  const supported = track.mode !== 'off' && track.available;
  return <Card variant="outlined"><CardContent><Stack spacing={2}>
    <Typography fontWeight={800}>動画音声 · {track.item_id} · {track.mode === 'dialogue_and_sound' ? '音・台詞' : track.mode === 'natural_sound' ? '環境音' : 'オフ'}</Typography>
    <video controls preload="none" src={videoUrl} style={{ width: '100%', maxHeight: 280 }} aria-label={`${track.item_id} 動画と音声のプレビュー`} />
    {!supported && <Alert severity="info">この動画の生成契約ではネイティブ音声を使用しません。</Alert>}
    <Stack direction="row" useFlexGap flexWrap="wrap" gap={2}>
      <TextField label="音量（dB）" type="number" size="small" value={draft.volume_db} disabled={disabled || !supported}
        slotProps={{ htmlInput: { min: -60, max: 36, step: 1 } }} onChange={event => patch({ volume_db: Number(event.target.value) })} sx={{ width: 140 }} />
      <TextField label="フェードイン（秒）" type="number" size="small" value={draft.fade_in_seconds} disabled={disabled || !supported}
        slotProps={{ htmlInput: { min: 0, max: 60, step: 0.1 } }} onChange={event => patch({ fade_in_seconds: Number(event.target.value) })} sx={{ width: 160 }} />
      <TextField label="フェードアウト（秒）" type="number" size="small" value={draft.fade_out_seconds} disabled={disabled || !supported}
        slotProps={{ htmlInput: { min: 0, max: 60, step: 0.1 } }} onChange={event => patch({ fade_out_seconds: Number(event.target.value) })} sx={{ width: 170 }} />
      {track.mode === 'dialogue_and_sound' && <TextField select label="台詞とナレーションの重なり" size="small" value={draft.overlap_policy} disabled={disabled}
        onChange={event => patch({ overlap_policy: event.target.value as NativeAudioSettings['overlap_policy'] })} sx={{ minWidth: 240 }}>
        <MenuItem value="preserve">両方をそのまま再生</MenuItem><MenuItem value="duck_narration">台詞中はナレーションを下げる</MenuItem>
      </TextField>}
    </Stack>
    <Stack direction="row" spacing={1} alignItems="center">
      <FormControlLabel control={<Checkbox checked={draft.enabled} disabled={disabled || !supported} onChange={(_, enabled) => patch({ enabled })} />} label="最終動画に使用" />
      <Button disabled={disabled || !supported} variant="outlined" onClick={() => void onSave(draft)}>設定を保存</Button>
    </Stack>
  </Stack></CardContent></Card>;
}

function AddSoundCue({ targets, duration, disabled, onCreate }: { targets: { item_id: string; start_seconds: number }[]; duration: number; disabled: boolean; onCreate: (value: object) => Promise<void> }) {
  const [kind, setKind] = useState<'bgm' | 'se'>('se');
  const [metadata, setMetadata] = useState<CueMetadata>({ label: '', source_selector: 'full_run', purpose: '', perspective: '', timing_reason: '' });
  const [prompt, setPrompt] = useState('');
  const [start, setStart] = useState(0);
  const [length, setLength] = useState(Math.min(3, duration));
  const [generationLength, setGenerationLength] = useState(3);
  return <Card variant="outlined"><CardContent><Stack spacing={2}>
    <Typography fontWeight={800}>音を追加</Typography>
    <Stack direction="row" spacing={2}>
      <TextField select label="種類" value={kind} disabled={disabled} onChange={e => setKind(e.target.value as 'bgm' | 'se')}><MenuItem value="se">SE</MenuItem><MenuItem value="bgm">BGM</MenuItem></TextField>
      <TextField select label="対象" value={metadata.source_selector} sx={{ minWidth: 180 }} disabled={disabled} onChange={e => { setMetadata({ ...metadata, source_selector: e.target.value }); setStart(targets.find(t => t.item_id === e.target.value)?.start_seconds || 0); }}>
        <MenuItem value="full_run">全編</MenuItem>{targets.map(t => <MenuItem key={t.item_id} value={t.item_id}>{t.item_id}</MenuItem>)}
      </TextField>
    </Stack>
    {([['label', '音の名前'], ['purpose', '狙う効果・必要な理由'], ['perspective', '音の視点'], ['timing_reason', '音が入る・終わる理由']] as const).map(([key,label]) => <TextField key={key} label={label} value={metadata[key]} disabled={disabled} onChange={e => setMetadata({ ...metadata, [key]: e.target.value })} />)}
    <TextField label="生成指示" multiline minRows={2} value={prompt} disabled={disabled} onChange={e => setPrompt(e.target.value)} />
    <Stack direction="row" spacing={2}>
      <TextField label="開始位置（全編の秒）" type="number" value={start} disabled={disabled} onChange={e => setStart(Number(e.target.value))} />
      <TextField label="再生する長さ（秒）" type="number" value={length} disabled={disabled} onChange={e => setLength(Number(e.target.value))} />
      <TextField label="生成する長さ（秒）" type="number" value={generationLength} disabled={disabled} onChange={e => setGenerationLength(Number(e.target.value))} />
    </Stack>
    <Button disabled={disabled || !validCueMetadata(metadata) || !prompt.trim() || start < 0 || length <= 0 || start + length > duration || generationLength < (kind === 'bgm' ? 3 : .5) || generationLength > (kind === 'bgm' ? 600 : 30)} onClick={() => void onCreate({ ...metadata, kind, prompt, start_seconds: start, duration_seconds: length, generation_duration_seconds: generationLength, volume_db: -18, fade_in_seconds: 0, fade_out_seconds: 0, loop: false })}>下書きを追加（音声は生成しません）</Button>
  </Stack></CardContent></Card>;
}

export function SoundDesignPanel({ runId, jsonFetch, audioFileUrl, videoFileUrl, onReady, onBusy }: Props) {
  const [data, setData] = useState<SoundStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [instructions, setInstructions] = useState('');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState('');
  const [dirtyCues, setDirtyCues] = useState<Record<string, boolean>>({});
  const onDirty = useCallback((id: string, value: boolean) => setDirtyCues(current => current[id] === value ? current : { ...current, [id]: value }), []);
  const hasUnsavedChanges = Object.values(dirtyCues).some(Boolean);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const apply = useCallback((value: SoundStatus) => {
    if (mounted.current) { setData(value); onReady(value.ready); }
  }, [onReady]);
  const refresh = useCallback(async () => {
    if (!runId) return;
    apply(await jsonFetch<SoundStatus>(`/api/image-gen/sound-design?run_id=${encodeURIComponent(runId)}`));
  }, [apply, jsonFetch, runId]);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    if (runId) {
      setBusy(true);
      void jsonFetch<SoundStatus>(`/api/image-gen/sound-design?run_id=${encodeURIComponent(runId)}`, { signal: controller.signal })
        .then(apply).catch(e => { if (!controller.signal.aborted) setError(String(e)); })
        .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }
    return () => { mounted.current = false; controller.abort(); };
  }, [apply, jsonFetch, runId]);
  const post = async (action: string, extra: object, source = data) => {
    if (!source) throw new Error('動画情報を再読込してください');
    return jsonFetch<SoundStatus>(`/api/image-gen/sound-design/${action}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId,
        video_set_hash: source.context.video_set_hash, revision: source.plan?.revision ?? 0, ...extra }) });
  };
  const act = async (operation: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); onBusy(true);
    try { await operation(); } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : String(e));
      try { await refresh(); } catch { /* Keep the original actionable error. */ }
    } finally { inFlight.current = false; if (mounted.current) setBusy(false); onBusy(false); }
  };
  return <Stack spacing={2} sx={{ gridColumn: '1 / -1', minWidth: 0 }}>
    <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
      <Typography variant="h6">BGM・SE</Typography>
      <Chip label="p860" size="small" />
      {data?.ready && <Chip label="設定確定済み・最終結合へ進めます" color="success" />}
      <Button disabled={busy || !runId || hasUnsavedChanges} onClick={() => void act(refresh)}>再読込</Button>
    </Stack>
    <Typography variant="body2" color="text.secondary">動画を承認後、設計書と物語を読んだLLMで音響案を作るか、必要な音を追加します。同じcutに複数のSEを配置できます。音声生成と採用は別の操作です。</Typography>
    {busy && <LinearProgress aria-label="BGM・SEを処理中" />}
    {error && <Alert severity="error">{error}</Alert>}
    {data?.blockedReason && <Alert severity="info">{data.blockedReason}</Alert>}
    {!runId && <Typography>作品を選択してください。</Typography>}
    {data && !data.approved && data.context.videos.length > 0 && <>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 2 }}>
        {data.context.videos.map(video => <Box key={video.item_id}>
          <Typography variant="body2">{video.item_id} · {video.duration_seconds}秒</Typography>
          <video controls preload="none" src={videoFileUrl(runId, video.path)} style={{ width: '100%' }} aria-label={video.item_id} />
        </Box>)}
      </Box>
      <Button variant="contained" disabled={busy} onClick={() => void act(async () => apply(await post('approve-video', {})))}>この動画一式を承認してBGM・SEへ</Button>
    </>}
    {data?.approved && <>
      <TextField label="音響設計への要望" multiline minRows={2} value={instructions} disabled={busy} onChange={e => setInstructions(e.target.value)} helperText="例：終幕は安心と余韻を大切に。既存の採用音は保持して、新しい案だけ追加します。" />
      <Stack direction="row" spacing={1}>
        <Button variant="contained" disabled={busy || hasUnsavedChanges} onClick={() => void act(async () => apply(await post('design', { instructions })))}>LLMで音響案を設計して追加</Button>
        <Button disabled={busy || hasUnsavedChanges} onClick={() => setAdding(v => !v)}>{adding ? '追加フォームを閉じる' : 'BGM・SEを手動追加'}</Button>
      </Stack>
      <Typography variant="caption" color="text.secondary">設計はLLMを使用します。音声生成APIは呼びません。不要な下書きは削除でき、採用音源は自動で置き換えません。</Typography>
      {data.plan?.designs?.map(design => <Alert key={design.id} severity="info"><Typography>{design.intent}</Typography>{design.silence_regions.map((r,i) => <Typography key={i} variant="body2">{r.start_seconds}〜{r.start_seconds+r.duration_seconds}秒 · {r.mode} · {r.reason}（意図のメモ・自動ミュートではありません）</Typography>)}</Alert>)}
      {adding && <AddSoundCue targets={data.context.videos} duration={data.context.duration_seconds} disabled={busy || hasUnsavedChanges} onCreate={cue => act(async () => { apply(await post('cue-create', { cue })); setAdding(false); })} />}
      <Typography variant="subtitle1" fontWeight={800}>動画の元音声</Typography>
      {data.plan?.native_tracks?.map(track => <NativeAudioCard key={track.item_id} track={track} disabled={busy}
        videoUrl={videoFileUrl(runId, track.path)} onDirty={onDirty}
        onSave={settings => act(async () => apply(await post('native-audio', { item_id: track.item_id, settings })))} />)}
      <Alert severity="info">音声の生成にはElevenLabsを使用します。生成しただけでは採用されません。</Alert>
      {data.plan?.cues.map(cue => <SoundCueCard key={cue.id} cue={cue} disabled={busy} onDirty={onDirty} targets={data.context.videos} url={path => audioFileUrl(runId, path)}
        onDelete={() => act(async () => apply(await post('cue-delete', { item_id: cue.id })))}
        onSave={(settings, metadata) => act(async () => apply(await post('cue', { item_id: cue.id, settings, metadata })))}
        onGenerate={(settings, metadata) => act(async () => {
          const saved = await post('cue', { item_id: cue.id, settings, metadata }); apply(saved);
          const result = await post('generate', { item_id: cue.id }, saved) as unknown as { candidates: Candidate[] };
          await refresh();
          const failed = result.candidates.find(candidate => candidate.status !== 'completed');
          if (failed) throw new Error(failed.error || '音声生成に失敗しました。再生成できます。');
        })} />)}
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <Button disabled={busy || hasUnsavedChanges || !(data.plan?.cues.some(cue => cue.enabled) || data.plan?.native_tracks?.some(track => track.enabled))} variant="contained"
          onClick={() => void act(async () => apply(await post('complete', { without_sound: false })))}>採用した音で確定（未採用は使わない）</Button>
        <Button disabled={busy || hasUnsavedChanges} variant="outlined" onClick={() => void act(async () => apply(await post('complete', { without_sound: true })))}>BGM・SEなしで確定</Button>
      </Stack>
      {hasUnsavedChanges && <Alert severity="info">未保存の設定があります。各カードの「設定を保存」を押してから確定してください。</Alert>}
      <Typography variant="caption" color="text.secondary">設定を変更した場合は各カードで保存し、もう一度確定してください。動画・尺が変わると再承認が必要です。</Typography>
    </>}
  </Stack>;
}
