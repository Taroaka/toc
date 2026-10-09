import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

export type ProductionKind = 'image' | 'video';
export type NormalizedRegion = { x: number; y: number; width: number; height: number };
export type VideoEditSettings = {
  start_seconds: number; duration_seconds: number; brightness: number; contrast: number;
  saturation: number; gamma: number; fade_in_seconds: number; fade_out_seconds: number;
};
export type ProductionContextIdentity = { runId: string; itemId: string; kind: ProductionKind };

export function sameProductionContextIdentity(a: ProductionContextIdentity, b: ProductionContextIdentity): boolean {
  return a.runId === b.runId && a.itemId === b.itemId && a.kind === b.kind;
}

export function normalizeRegions(regions: NormalizedRegion[]): NormalizedRegion[] {
  return regions.map(region => {
    const x = Math.max(0, Math.min(1, region.x));
    const y = Math.max(0, Math.min(1, region.y));
    const right = Math.max(x, Math.min(1, region.x + region.width));
    const bottom = Math.max(y, Math.min(1, region.y + region.height));
    return { x, y, width: right - x, height: bottom - y };
  }).filter(region => region.width > 0 && region.height > 0);
}

export function validateRegionSelection(regions: NormalizedRegion[]): NormalizedRegion[] {
  if (!regions.length || regions.length > 32 || regions.some(region =>
    ![region.x, region.y, region.width, region.height].every(Number.isFinite)
    || region.x < 0 || region.y < 0 || region.width <= 0 || region.height <= 0
    || region.x + region.width > 1 || region.y + region.height > 1)) {
    throw new Error('変更範囲は画像の内側にある矩形を1〜32個指定してください。');
  }
  return regions.map(region => ({ ...region }));
}

export function normalizeVideoSettings(settings: VideoEditSettings, sourceDuration: number): VideoEditSettings {
  const limits: Record<keyof VideoEditSettings, [number, number]> = {
    start_seconds: [0, sourceDuration], duration_seconds: [0.01, sourceDuration],
    brightness: [-0.25, 0.25], contrast: [0.5, 2], saturation: [0, 2], gamma: [0.5, 2],
    fade_in_seconds: [0, sourceDuration], fade_out_seconds: [0, sourceDuration],
  };
  for (const [key, [min, max]] of Object.entries(limits) as [keyof VideoEditSettings, [number, number]][]) {
    const value = settings[key];
    const labels: Record<keyof VideoEditSettings, string> = {
      start_seconds: '開始位置', duration_seconds: '編集尺', brightness: '明るさ', contrast: 'コントラスト',
      saturation: '彩度', gamma: 'ガンマ', fade_in_seconds: 'フェードイン', fade_out_seconds: 'フェードアウト',
    };
    if (!Number.isFinite(value) || value < min || value > max) throw new Error(`${labels[key]}は ${min}〜${max} の範囲で指定してください。`);
  }
  if (settings.start_seconds + settings.duration_seconds > sourceDuration + 1e-6) {
    throw new Error('開始位置と長さが元動画の範囲を超えています。');
  }
  if (settings.fade_in_seconds > settings.duration_seconds || settings.fade_out_seconds > settings.duration_seconds) {
    throw new Error('フェード時間は編集後の長さ以内にしてください。');
  }
  return { ...settings };
}

export function canAdoptVideo(editDuration: number, requiredDuration: number): boolean {
  return Number.isFinite(editDuration) && Number.isFinite(requiredDuration)
    && requiredDuration > 0 && editDuration + 0.05 >= requiredDuration;
}

type Candidate = { path: string; sha256: string; label: string; current?: boolean; duration_seconds?: number; width?: number; height?: number };
type Reference = { path: string; sha256: string; label: string; width?: number; height?: number };
type Note = { candidate_path?: string; candidate_sha256?: string; disposition?: string; problem?: string; change?: string; result?: string; request_revision?: string; is_stale?: boolean; created_at?: string };
type Geometry = {
  schema_version: 'shot_geometry_v1';
  camera: { position: [number, number, number]; target: [number, number, number]; vertical_fov_degrees: number; aspect_ratio: number };
  subjects: { asset_id: string; name: string; position: [number, number, number]; size: [number, number, number] }[];
  lights: { name: string; position: [number, number, number]; range_m: number }[];
};
type GeometryPreview = {
  camera_view?: { asset_id: string; name: string; x: number; y: number; width: number; height: number; depth: number; visible: boolean }[];
  top_view?: { subjects?: { asset_id: string; name: string; x: number; y: number; width: number; height: number }[]; lights?: { name: string; x: number; y: number; range_radius_x: number; range_radius_y: number }[]; camera?: { x: number; y: number }; target?: { x: number; y: number }; bounds_m?: { min_x: number; max_x: number; min_y: number; max_y: number } };
};
type ToolContext = {
  run_id: string; item_id: string; kind: ProductionKind; request_revision: string; candidates: Candidate[]; references: Reference[];
  notes: { revision: number; entries: Note[] }; variants: Record<string, unknown>[]; video_edits: Record<string, unknown>[];
  geometry: Geometry | null; geometry_revision: number; geometry_preview: GeometryPreview | null; geometry_stale?: boolean;
  allowed_assets: { id: string; name: string }[]; planned_duration_seconds: number; selected_video_path: string | null; selection_error?: string | null;
};
type Props = {
  runId: string; itemId: string; kind: ProductionKind;
  jsonFetch: <T>(input: RequestInfo, init?: RequestInit) => Promise<T>;
  mediaUrl: (path: string, kind: ProductionKind) => string;
  onVideoSelected?: (path: string) => void;
  onReferenceCreated?: (path: string) => void;
};

const initialGeometry = (): Geometry => ({ schema_version: 'shot_geometry_v1',
  camera: { position: [0, -6, 2], target: [0, 0, 1], vertical_fov_degrees: 45, aspect_ratio: 16 / 9 }, subjects: [], lights: [] });
const pathOf = (row: Record<string, unknown>) => typeof row.output_path === 'string' ? row.output_path : typeof row.path === 'string' ? row.path : '';
const labelOf = (path: string) => path.split('/').pop() || path;
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

function Media({ path, kind, mediaUrl, label }: { path?: string | null; kind: ProductionKind; mediaUrl: Props['mediaUrl']; label: string }) {
  if (!path) return <Box sx={{ minHeight: 150, display: 'grid', placeItems: 'center', bgcolor: 'action.hover', borderRadius: 1 }}><Typography color="text.secondary">プレビューなし</Typography></Box>;
  const url = mediaUrl(path, kind);
  return kind === 'video'
    ? <video controls preload="none" src={url} aria-label={label} style={{ width: '100%', maxHeight: 300, background: '#111', borderRadius: 8 }} />
    : <img src={url} alt={label} style={{ display: 'block', width: '100%', maxHeight: 360, objectFit: 'contain', background: '#111', borderRadius: 8 }} />;
}

function VectorFields({ label, value, disabled, onChange }: { label: string; value: [number, number, number]; disabled: boolean; onChange: (value: [number, number, number]) => void }) {
  return <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
    <Typography variant="body2" sx={{ minWidth: 90 }}>{label}</Typography>
    {value.map((component, index) => <TextField key={index} label={['X', 'Y', 'Z'][index]} type="number" size="small" value={component} disabled={disabled}
      onChange={event => onChange(value.map((part, i) => i === index ? Number(event.target.value) : part) as [number, number, number])} sx={{ width: 92 }} />)}
  </Stack>;
}

function GeometryDiagram({ preview, aspectRatio }: { preview: GeometryPreview | null; aspectRatio: number }) {
  const markerId = `camera-arrow-${useId().replace(/:/g, '')}`;
  const view = preview?.top_view;
  const bounds = view?.bounds_m;
  const topAspectRatio = bounds ? Math.max(0.01, (bounds.max_x - bounds.min_x) / (bounds.max_y - bounds.min_y)) : 1;
  const cameraAspectRatio = Number.isFinite(aspectRatio) && aspectRatio > 0 ? aspectRatio : 1;
  return <Stack spacing={1}>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
    <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="caption">上面図 · XY平面</Typography><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="配置の上面図" style={{ display: 'block', width: '100%', aspectRatio: `${topAspectRatio}`, border: '1px solid #aaa', borderRadius: 8, background: '#f8f8f8' }}>
      <defs><marker id={markerId} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#333" /></marker></defs>
      {view?.lights?.map((light, index) => <g key={`light-${index}`}><ellipse cx={light.x * 100} cy={light.y * 100} rx={light.range_radius_x * 100} ry={light.range_radius_y * 100} fill="#ffc107" fillOpacity=".12" stroke="#d69e00" strokeDasharray="2 2" /><circle cx={light.x * 100} cy={light.y * 100} r="2" fill="#d69e00" /></g>)}
      {view?.subjects?.map((subject, index) => <g key={`subject-${index}`}><rect x={subject.x * 100} y={subject.y * 100} width={Math.max(subject.width * 100, 2)} height={Math.max(subject.height * 100, 2)} fill="#4f86c6" fillOpacity=".55" stroke="#24527a" /><title>{subject.name}</title></g>)}
      {view?.camera && view.target && <line x1={view.camera.x * 100} y1={view.camera.y * 100} x2={view.target.x * 100} y2={view.target.y * 100} stroke="#333" strokeWidth="1.5" markerEnd={`url(#${markerId})`} />}
    </svg></Box>
    <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="caption">カメラから見た概略</Typography><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="カメラ視点の配置図" style={{ display: 'block', width: '100%', aspectRatio: `${cameraAspectRatio}`, border: '1px solid #aaa', borderRadius: 8, background: '#f8f8f8' }}>
      {preview?.camera_view?.filter(item => item.visible).map((item, index) => <g key={`view-${index}`}><rect x={item.x * 100} y={item.y * 100} width={item.width * 100} height={item.height * 100} fill="#4f86c6" fillOpacity=".55" stroke="#24527a" /><title>{item.name} · 奥行き {item.depth.toFixed(1)}m</title></g>)}
    </svg></Box>
    </Stack>
    <Stack direction="row" spacing={1.5} useFlexGap flexWrap="wrap" sx={{ flexBasis: '100%' }}>
      {view?.subjects?.map(subject => <Stack key={`legend-subject-${subject.asset_id}`} direction="row" spacing={0.75} alignItems="center"><Box aria-hidden="true" sx={{ width: 10, height: 10, bgcolor: '#4f86c6', border: '1px solid #24527a' }} /><Typography variant="caption">{subject.name}</Typography></Stack>)}
      {view?.lights?.map(light => <Stack key={`legend-light-${light.name}`} direction="row" spacing={0.75} alignItems="center"><Box aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#ffc107', border: '1px solid #d69e00' }} /><Typography variant="caption">ライト：{light.name}</Typography></Stack>)}
    </Stack>
  </Stack>;
}

export function ProductionToolsPanel({ runId, itemId, kind, jsonFetch, mediaUrl, onVideoSelected, onReferenceCreated }: Props) {
  const identity: ProductionContextIdentity = { runId, itemId, kind };
  const identityRef = useRef(identity);
  identityRef.current = identity;
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState<ToolContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [candidateA, setCandidateA] = useState('');
  const [candidateB, setCandidateB] = useState('');
  const [basePath, setBasePath] = useState('');
  const [editedPath, setEditedPath] = useState('');
  const [disposition, setDisposition] = useState('undecided');
  const [problem, setProblem] = useState('');
  const [change, setChange] = useState('');
  const [result, setResult] = useState('');
  const [stateDescription, setStateDescription] = useState('');
  const [regions, setRegions] = useState<NormalizedRegion[]>([]);
  const [regionStart, setRegionStart] = useState<{ x: number; y: number } | null>(null);
  const imageWrap = useRef<HTMLDivElement>(null);
  const [settings, setSettings] = useState<VideoEditSettings>({ start_seconds: 0, duration_seconds: 5, brightness: 0, contrast: 1, saturation: 1, gamma: 1, fade_in_seconds: 0, fade_out_seconds: 0 });
  const [geometry, setGeometry] = useState<Geometry>(initialGeometry);

  const applyContext = (source: ProductionContextIdentity, value: ToolContext): boolean => {
    if (!sameProductionContextIdentity(source, identityRef.current) || value.run_id !== source.runId || value.item_id !== source.itemId || value.kind !== source.kind) return false;
    setData(value);
    setCandidateA(current => value.candidates.some(c => c.path === current) ? current : value.candidates[0]?.path || '');
    setCandidateB(current => value.candidates.some(c => c.path === current) ? current : value.candidates[1]?.path || value.candidates[0]?.path || '');
    setBasePath(current => value.references.some(ref => ref.path === current) ? current : value.references[0]?.path || '');
    setEditedPath(current => value.candidates.some(candidate => candidate.path === current) ? current : value.candidates[0]?.path || '');
    setGeometry(value.geometry || initialGeometry());
    return true;
  };
  const refresh = async (source: ProductionContextIdentity = identityRef.current, signal?: AbortSignal) => {
    const query = new URLSearchParams({ run_id: source.runId, item_id: source.itemId, kind: source.kind });
    const next = await jsonFetch<ToolContext>(`/api/image-gen/production-tools?${query}`, signal ? { signal } : undefined);
    applyContext(source, next);
    return next;
  };
  useEffect(() => {
    setSaving(false);
    setError('');
    if (!expanded || !runId) return;
    const controller = new AbortController();
    const source = identityRef.current;
    setData(null); setLoading(true); setError('');
    void refresh(source, controller.signal).catch(reason => { if (!controller.signal.aborted && sameProductionContextIdentity(source, identityRef.current)) setError(errorText(reason)); })
      .finally(() => { if (!controller.signal.aborted && sameProductionContextIdentity(source, identityRef.current)) setLoading(false); });
    return () => controller.abort();
  // Loading remains tied to the panel's identity; refresh is intentionally local to this component.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, runId, itemId, kind]);

  const mutate = async (source: ProductionContextIdentity, path: string, body: object): Promise<ToolContext> => jsonFetch<ToolContext>(`/api/image-gen/production-tools/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: source.runId, item_id: source.itemId, ...body }),
  });
  const act = async (operation: (source: ProductionContextIdentity) => Promise<void>) => {
    if (saving) return;
    const source = identityRef.current;
    if (!data || !sameProductionContextIdentity({ runId: data.run_id, itemId: data.item_id, kind: data.kind }, source)) return;
    setSaving(true); setError('');
    try { await operation(source); } catch (reason) {
      if (sameProductionContextIdentity(source, identityRef.current)) {
        setError(errorText(reason));
        try { await refresh(source); } catch { /* Preserve the operation error. */ }
      }
    } finally { if (sameProductionContextIdentity(source, identityRef.current)) setSaving(false); }
  };
  const candidate = (path: string) => data?.candidates.find(item => item.path === path);
  const reference = (path: string) => data?.references.find(item => item.path === path);
  const selectedA = candidate(candidateA);
  const selectedB = candidate(candidateB);
  const base = reference(basePath);
  const edited = candidate(editedPath);
  const baseIdentity = base ? `${base.path}\u0000${base.sha256}` : '';
  useEffect(() => {
    setRegions([]);
    setRegionStart(null);
  }, [baseIdentity]);
  const variants = data?.variants || [];
  const videoEdits = data?.video_edits || [];
  const requiredDuration = data?.planned_duration_seconds || 0;
  const imageUrl = (path: string) => mediaUrl(path, 'image');
  const updateCamera = (field: keyof Geometry['camera'], value: number | [number, number, number]) => setGeometry(current => ({ ...current,
    camera: { ...current.camera, [field]: value } }));
  const assetOptions = data?.allowed_assets || [];
  const notes = data?.notes.entries || [];
  const noted = useMemo(() => new Set((data?.candidates || []).map(c => `${c.path}\u0000${c.sha256}`)), [data?.candidates]);

  const pointFromEvent = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = imageWrap.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
  };
  const drawRegion = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = regionStart; const end = pointFromEvent(event);
    if (!start || !end) return;
    const rect = normalizeRegions([{ x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(start.x - end.x), height: Math.abs(start.y - end.y) }])[0];
    if (rect) setRegions(current => [...current, rect]);
    setRegionStart(null);
  };
  const patchSettings = (key: keyof VideoEditSettings, value: number) => setSettings(current => ({ ...current, [key]: value }));

  return <Accordion expanded={expanded} onChange={(_, value) => setExpanded(value)} disableGutters sx={{ gridColumn: '1 / -1', minWidth: 0, border: '1px solid', borderColor: 'divider', borderRadius: '12px !important', '&:before': { display: 'none' } }}>
    <AccordionSummary expandIcon={<ExpandMoreIcon />}><Stack direction="row" spacing={1} alignItems="center"><Typography fontWeight={800}>制作補助ツール</Typography><Chip size="small" label="ローカル処理" /></Stack></AccordionSummary>
    <AccordionDetails><Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">候補の比較、メモ、既存素材の編集、配置プレビューを行います。新しいAI生成は行いません。</Typography>
      {loading && <Typography role="status">読み込み中…</Typography>}
      {error && <Alert severity="error">{error}</Alert>}
      {data?.selection_error && <Alert severity="warning">現在の動画選択は無効です：{data.selection_error}。候補を選び直してください。</Alert>}
      {!runId && <Alert severity="info">作品を選択してください。</Alert>}
      {data && <>
        <Card variant="outlined"><CardContent><Stack spacing={1.5}>
          <Typography variant="subtitle1" fontWeight={800}>候補を比較してメモ</Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 2 }}>
            {[{ value: candidateA, set: setCandidateA, label: '候補 A' }, { value: candidateB, set: setCandidateB, label: '候補 B' }].map((select, index) => <Stack key={select.label} spacing={1}>
              <TextField select label={select.label} size="small" value={select.value} onChange={event => select.set(event.target.value)}>
                {data.candidates.map(item => <MenuItem key={item.path} value={item.path}>{item.label || labelOf(item.path)}</MenuItem>)}
              </TextField>
              <Media path={index === 0 ? selectedA?.path : selectedB?.path} kind={kind} mediaUrl={mediaUrl} label={select.label} />
              {(index === 0 ? selectedA : selectedB) && <Typography variant="caption" color="text.secondary">{(index === 0 ? selectedA : selectedB)?.duration_seconds ? `${(index === 0 ? selectedA : selectedB)?.duration_seconds?.toFixed(2)}秒 · ` : ''}{(index === 0 ? selectedA : selectedB)?.width || '—'} × {(index === 0 ? selectedA : selectedB)?.height || '—'}</Typography>}
            </Stack>)}
          </Box>
          <Stack direction="row" useFlexGap flexWrap="wrap" gap={1}>
            <TextField select size="small" label="所感" value={disposition} onChange={event => setDisposition(event.target.value)} sx={{ minWidth: 140 }}>
              <MenuItem value="keep">残す</MenuItem><MenuItem value="reject">見送る</MenuItem><MenuItem value="undecided">保留</MenuItem>
            </TextField>
            <TextField size="small" label="問題" value={problem} onChange={event => setProblem(event.target.value)} sx={{ flex: 1, minWidth: 170 }} />
            <TextField size="small" label="試す変更" value={change} onChange={event => setChange(event.target.value)} sx={{ flex: 1, minWidth: 170 }} />
            <TextField size="small" label="結果" value={result} onChange={event => setResult(event.target.value)} sx={{ flex: 1, minWidth: 170 }} />
            <Button variant="contained" disabled={saving || !data || !selectedA || selectedA.current === false} onClick={() => void act(async source => {
              const fresh = await mutate(source, 'notes', { kind: source.kind, candidate_path: selectedA!.path, candidate_sha256: selectedA!.sha256,
                expected_revision: data.notes.revision, disposition, problem, change, result });
              applyContext(source, fresh);
            })}>候補 A のメモを保存</Button>
          </Stack>
          {!!notes.length && <Stack spacing={0.75}><Typography variant="body2" fontWeight={700}>メモ履歴</Typography>{notes.map((note, index) => {
            const stale = Boolean(note.is_stale) || !noted.has(`${note.candidate_path || ''}\u0000${note.candidate_sha256 || ''}`)
              || (note.request_revision !== undefined && note.request_revision !== data.request_revision);
            return <Box key={`${note.created_at || 'note'}-${index}`} sx={{ p: 1, borderRadius: 1, bgcolor: 'action.hover' }}>
              <Stack direction="row" spacing={1} alignItems="center"><Typography variant="body2">{note.disposition || 'メモ'} · {labelOf(note.candidate_path || '')}</Typography>{stale && <Chip size="small" label="古い候補へのメモ" />}</Stack>
              <Typography variant="caption" color="text.secondary">{[note.problem, note.change, note.result].filter(Boolean).join(' → ') || '詳細なし'}</Typography>
            </Box>;
          })}</Stack>}
          <Typography variant="caption" color="text.secondary">メモは候補の評価記録です。候補の自動採用や生成は行いません。</Typography>
        </Stack></CardContent></Card>

        {kind === 'image' && <Card variant="outlined"><CardContent><Stack spacing={1.5}>
          <Typography variant="subtitle1" fontWeight={800}>既存画像の部分差し替え</Typography>
          <Alert severity="info">元画像の選択範囲だけを既存の編集候補で置き換えます。範囲外の画素と元画像を保ち、新しいAI生成は行いません。</Alert>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
            <TextField select size="small" label="基準画像" value={basePath} onChange={event => setBasePath(event.target.value)} sx={{ flex: 1 }}>
              {data.references.map(item => <MenuItem key={item.path} value={item.path}>{item.label || labelOf(item.path)}</MenuItem>)}
            </TextField>
            <TextField select size="small" label="差し替え画像" value={editedPath} onChange={event => setEditedPath(event.target.value)} sx={{ flex: 1 }}>
              {data.candidates.map(item => <MenuItem key={item.path} value={item.path}>{item.label || labelOf(item.path)}</MenuItem>)}
            </TextField>
          </Stack>
          {base && edited && (base.width && edited.width && (base.width !== edited.width || base.height !== edited.height)) && <Alert severity="warning">画像サイズが異なるため、この組み合わせは使えません。</Alert>}
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2}>
            <Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="caption">基準画像をドラッグして矩形を追加</Typography>
              <Box ref={imageWrap} sx={{ position: 'relative', display: 'block', width: '100%', maxWidth: 640, touchAction: 'none', cursor: 'crosshair' }}
                onPointerDown={event => { const point = pointFromEvent(event); if (point) { setRegionStart(point); event.currentTarget.setPointerCapture(event.pointerId); } }}
                onPointerUp={drawRegion} onPointerCancel={() => setRegionStart(null)}>
                {base && <img src={imageUrl(base.path)} alt="基準画像" style={{ display: 'block', width: '100%', height: 'auto', background: '#111', borderRadius: 8 }} />}
                {regions.map((region, index) => <Box key={`region-${index}`} sx={{ position: 'absolute', left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.width * 100}%`, height: `${region.height * 100}%`, border: '2px solid #ffca28', bgcolor: 'rgba(255,202,40,.18)', pointerEvents: 'none' }} />)}
              </Box>
            </Box>
            <Stack spacing={1} sx={{ minWidth: 220 }}><Typography variant="caption">矩形の座標（画像全体に対する 0〜1）</Typography>
              {regions.map((region, index) => <Stack key={`numeric-${index}`} direction="row" spacing={0.5} alignItems="center">
                {(['x', 'y', 'width', 'height'] as const).map(key => <TextField key={key} label={key} type="number" size="small" value={region[key]} slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }} sx={{ width: 76 }}
                  onChange={event => setRegions(current => current.map((item, i) => i === index ? { ...item, [key]: Number(event.target.value) } : item))} />)}
                <Button size="small" onClick={() => setRegions(current => current.filter((_, i) => i !== index))} aria-label={`矩形 ${index + 1} を削除`}>削除</Button>
              </Stack>)}
              <Button size="small" onClick={() => setRegions(current => [...current, { x: 0.35, y: 0.3, width: 0.3, height: 0.3 }])}>座標で矩形を追加</Button>
              <Button size="small" disabled={!regions.length} onClick={() => setRegions([])}>範囲をクリア</Button>
            </Stack>
          </Stack>
          <TextField label="変更後の状態" size="small" value={stateDescription} onChange={event => setStateDescription(event.target.value)} fullWidth />
          <Button variant="contained" disabled={saving || !base || !edited || edited.current === false || !regions.length || !stateDescription.trim() || (base.width !== undefined && edited.width !== undefined && (base.width !== edited.width || base.height !== edited.height))}
            onClick={() => void act(async source => { const fresh = await mutate(source, 'variant', { base_path: base!.path, edited_path: edited!.path,
              base_sha256: base!.sha256, edited_sha256: edited!.sha256, regions: validateRegionSelection(regions), state_description: stateDescription }); applyContext(source, fresh); })}>新しい派生画像を作成</Button>
          {variants.map((variant, index) => { const path = pathOf(variant); return <Box key={path || index} sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1 }}>
            <Stack spacing={1}><Stack direction="row" spacing={1} alignItems="center"><Typography fontWeight={700}>{String(variant.state_description || '派生画像')}</Typography>{Boolean(variant.stale) && <Chip label="元候補が更新済み" size="small" />}</Stack><Media path={path || null} kind="image" mediaUrl={mediaUrl} label="派生画像プレビュー" /><Typography variant="caption" color="text.secondary">派生画像は明示的に参照へ追加できます。元画像は変更しません。</Typography>
              {path && <Button size="small" variant="outlined" disabled={saving || Boolean(variant.stale)} onClick={() => {
                if (sameProductionContextIdentity({ runId: data.run_id, itemId: data.item_id, kind: data.kind }, identityRef.current)) onReferenceCreated?.(path);
              }}>参照に追加</Button>}</Stack>
          </Box>; })}
        </Stack></CardContent></Card>}

        {kind === 'video' && <Card variant="outlined"><CardContent><Stack spacing={1.5}>
          <Typography variant="subtitle1" fontWeight={800}>既存動画の編集と選択</Typography>
          <Alert severity="info">短い編集を確認用に作成できます。最終動画へ採用するには、現在のカット尺とナレーションを満たす必要があります。尺を黙って変更しません。</Alert>
          <TextField select size="small" label="編集元" value={candidateA} onChange={event => setCandidateA(event.target.value)} sx={{ maxWidth: 420 }}>
            {data.candidates.map(item => <MenuItem key={item.path} value={item.path}>{item.label || labelOf(item.path)}{item.duration_seconds ? ` · ${item.duration_seconds.toFixed(2)}秒` : ''}</MenuItem>)}
          </TextField>
          <Media path={selectedA?.path} kind="video" mediaUrl={mediaUrl} label="編集元の動画" />
          {selectedA && <Button size="small" variant="outlined" disabled={saving || selectedA.current === false || (selectedA.duration_seconds !== undefined && !canAdoptVideo(selectedA.duration_seconds, requiredDuration))}
            onClick={() => void act(async source => { const fresh = await mutate(source, 'select-video', { path: selectedA!.path, sha256: selectedA!.sha256 }); if (applyContext(source, fresh)) onVideoSelected?.(selectedA!.path); })}>
            {data.selected_video_path === selectedA.path ? '元候補を最終動画に選択済み' : 'この元候補を最終動画に選択'}
          </Button>}
          <Stack direction="row" useFlexGap flexWrap="wrap" gap={1}>
            {([['start_seconds', '開始位置（秒）', 0, selectedA?.duration_seconds || 600], ['duration_seconds', '編集尺（秒）', 0.01, selectedA?.duration_seconds || 600], ['brightness', '明るさ', -0.25, 0.25], ['contrast', 'コントラスト', 0.5, 2], ['saturation', '彩度', 0, 2], ['gamma', 'ガンマ', 0.5, 2], ['fade_in_seconds', 'フェードイン（秒）', 0, 600], ['fade_out_seconds', 'フェードアウト（秒）', 0, 600]] as [keyof VideoEditSettings, string, number, number][]).map(([key, label, min, max]) => <TextField key={key} type="number" label={label} size="small" value={settings[key]} slotProps={{ htmlInput: { min, max, step: key.endsWith('_seconds') ? 0.1 : 0.05 } }} onChange={event => patchSettings(key, Number(event.target.value))} sx={{ width: 155 }} />)}
          </Stack>
          <Button variant="contained" disabled={saving || !selectedA || selectedA.current === false} onClick={() => void act(async source => {
            const clean = normalizeVideoSettings(settings, selectedA!.duration_seconds || 0);
            const fresh = await mutate(source, 'video-edit', { source_path: selectedA!.path, source_sha256: selectedA!.sha256, settings: clean }); applyContext(source, fresh);
          })}>編集候補を作成</Button>
          {videoEdits.map((edit, index) => { const path = pathOf(edit); const duration = Number(edit.duration_seconds || (edit.settings as Record<string, unknown> | undefined)?.duration_seconds || 0); const covered = canAdoptVideo(duration, requiredDuration); const matching = candidate(edit.source_path as string); const stale = Boolean(edit.is_stale) || (edit.source_sha256 !== undefined && matching?.sha256 !== edit.source_sha256); const sha = typeof edit.sha256 === 'string' ? edit.sha256 : typeof edit.output_sha256 === 'string' ? edit.output_sha256 : '';
            return <Box key={path || index} sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1 }}><Stack spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap"><Typography fontWeight={700}>{String(edit.state_description || labelOf(path) || `編集 ${index + 1}`)} · {duration.toFixed(2)}秒</Typography>{stale && <Chip label="元動画が更新済み" size="small" />}{!covered && <Chip label={`現在のカット尺 ${requiredDuration.toFixed(2)}秒を満たしません`} color="warning" size="small" />}</Stack>
              <Media path={path || null} kind="video" mediaUrl={mediaUrl} label="編集結果" />
              {!!path && sha && <Button disabled={saving || stale || !covered} variant="outlined" onClick={() => void act(async source => {
                const fresh = await mutate(source, 'select-video', { path, sha256: sha }); if (applyContext(source, fresh)) onVideoSelected?.(path);
              })}>{data.selected_video_path === path ? '最終動画に選択済み' : '最終動画に選択'}</Button>}
            </Stack></Box>; })}
          <Typography variant="caption" color="text.secondary">選択後は、動画と音声の承認をもう一度行います。</Typography>
        </Stack></CardContent></Card>}

        <Card variant="outlined"><CardContent><Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center"><Typography variant="subtitle1" fontWeight={800}>空間配置プレビュー（任意）</Typography>{data.geometry_stale && <Chip size="small" label="以前の配置計画" color="warning" />}</Stack>
          {data.geometry_stale && <Alert severity="warning">この配置は現在の項目に結び付いていません。保存すると現在の項目に計画として再登録します。生成に反映するには、制作元の配置情報を明示的に更新して再構築してください。</Alert>}
          <Alert severity="info">配置は計画用プレビューです。生成に反映するには、制作元の配置情報を更新して再構築してください。光の円は指定レンジの図示で、照度の予測ではありません。</Alert>
          <VectorFields label="カメラ位置（m）" value={geometry.camera.position} disabled={saving} onChange={value => updateCamera('position', value)} />
          <VectorFields label="注視点（m）" value={geometry.camera.target} disabled={saving} onChange={value => updateCamera('target', value)} />
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <TextField label="垂直画角（度）" type="number" size="small" value={geometry.camera.vertical_fov_degrees} disabled={saving} onChange={event => updateCamera('vertical_fov_degrees', Number(event.target.value))} />
            <TextField label="アスペクト比" type="number" size="small" value={geometry.camera.aspect_ratio} disabled={saving} onChange={event => updateCamera('aspect_ratio', Number(event.target.value))} />
          </Stack>
          <Typography variant="body2" fontWeight={700}>被写体</Typography>
          {geometry.subjects.map((subject, index) => <Stack key={`subj-${index}`} spacing={1} sx={{ p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center"><TextField select label="素材" size="small" value={subject.asset_id} onChange={event => setGeometry(current => ({ ...current, subjects: current.subjects.map((item, i) => i === index ? { ...item, asset_id: event.target.value, name: assetOptions.find(asset => asset.id === event.target.value)?.name || item.name } : item) }))} sx={{ minWidth: 220 }}>
              {assetOptions.map(asset => <MenuItem key={asset.id} value={asset.id}>{asset.name}</MenuItem>)}
            </TextField><Button onClick={() => setGeometry(current => ({ ...current, subjects: current.subjects.filter((_, i) => i !== index) }))}>削除</Button></Stack>
            <VectorFields label="位置（m）" value={subject.position} disabled={saving} onChange={position => setGeometry(current => ({ ...current, subjects: current.subjects.map((item, i) => i === index ? { ...item, position } : item) }))} />
            <VectorFields label="寸法（m）" value={subject.size} disabled={saving} onChange={size => setGeometry(current => ({ ...current, subjects: current.subjects.map((item, i) => i === index ? { ...item, size } : item) }))} />
          </Stack>)}
          <Button size="small" disabled={!assetOptions.length} onClick={() => { const asset = assetOptions.find(option => !geometry.subjects.some(subject => subject.asset_id === option.id)); if (!asset) return; setGeometry(current => ({ ...current, subjects: [...current.subjects, { asset_id: asset.id, name: asset.name, position: [0, 0, 1], size: [1, 1, 2] }] })); }}>被写体を追加</Button>
          <Typography variant="body2" fontWeight={700}>ライト</Typography>
          {geometry.lights.map((light, index) => <Stack key={`light-${index}`} spacing={1} sx={{ p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
            <Stack direction="row" spacing={1}><TextField label="名前" size="small" value={light.name} onChange={event => setGeometry(current => ({ ...current, lights: current.lights.map((item, i) => i === index ? { ...item, name: event.target.value } : item) }))} /><TextField label="レンジ（m）" type="number" size="small" value={light.range_m} onChange={event => setGeometry(current => ({ ...current, lights: current.lights.map((item, i) => i === index ? { ...item, range_m: Number(event.target.value) } : item) }))} /><Button onClick={() => setGeometry(current => ({ ...current, lights: current.lights.filter((_, i) => i !== index) }))}>削除</Button></Stack>
            <VectorFields label="位置（m）" value={light.position} disabled={saving} onChange={position => setGeometry(current => ({ ...current, lights: current.lights.map((item, i) => i === index ? { ...item, position } : item) }))} />
          </Stack>)}
          <Button size="small" onClick={() => setGeometry(current => ({ ...current, lights: [...current.lights, { name: `ライト ${current.lights.length + 1}`, position: [0, -2, 3], range_m: 5 }] }))}>ライトを追加</Button>
          <GeometryDiagram preview={data.geometry_preview} aspectRatio={geometry.camera.aspect_ratio} />
          <Button variant="contained" disabled={saving} onClick={() => void act(async source => { const fresh = await mutate(source, 'geometry', { kind: source.kind, geometry, expected_revision: data.geometry_revision }); applyContext(source, fresh); })}>配置を保存してプレビュー更新</Button>
        </Stack></CardContent></Card>
      </>}
      {data && !data.candidates.length && !data.references.length && <Alert severity="info">この項目にはまだ画像・動画候補がありません。</Alert>}
    </Stack></AccordionDetails>
  </Accordion>;
}
