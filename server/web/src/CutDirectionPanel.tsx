import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  FormControlLabel,
  InputLabel,
  LinearProgress,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import { VideoPreparationPanel } from './VideoPreparationPanel';
import './cutDirectionPanel.css';

export type CutDirectionShot = {
  id: string;
  startSeconds: number;
  durationSeconds: number;
  intent: string;
  framing: string;
  visibleSubjects: string[];
  motion: string;
  referencePaths: string[];
  imagePath: string | null;
  videoPath: string | null;
};

export type CutDirectionCut = {
  id: string;
  cutId: string;
  intent: string;
  durationSeconds: number;
  narrationDurationSeconds: number | null;
  thumbnailPath: string | null;
  plan: Record<string, unknown> | null;
  shots: CutDirectionShot[];
  source: 'legacy' | 'shot_direction_v1';
};

export type CutDirectionScene = {
  sceneId: string;
  title: string;
  cuts: CutDirectionCut[];
};

export type CutDirectionResponse = {
  runId: string;
  revision: string;
  scenes: CutDirectionScene[];
};

type EditMode = 'plan' | 'instruction';

type CutDirectionSavePayload = {
  run_id: string;
  item_id: string;
  expected_revision: string;
  plan?: Record<string, unknown>;
  instruction?: string;
};

type JsonFetch = <T>(input: RequestInfo, init?: RequestInit) => Promise<T>;

type Props = {
  runId: string;
  jsonFetch: JsonFetch;
  imageFileUrl: (runId: string, path: string) => string;
  videoFileUrl: (runId: string, path: string) => string;
  selectedCutId?: string;
  onSelectCut?: (scene: CutDirectionScene, cut: CutDirectionCut) => void;
  onRefresh?: () => void | Promise<void>;
};

type SavePayloadInput = {
  runId: string;
  itemId: string;
  expectedRevision: string;
  mode: EditMode;
  value: string;
};

export function buildCutDirectionSavePayload(input: SavePayloadInput): CutDirectionSavePayload {
  const base = {
    run_id: input.runId,
    item_id: input.itemId,
    expected_revision: input.expectedRevision,
  };
  if (input.mode === 'instruction') {
    const instruction = input.value.trim();
    if (!instruction) throw new Error('映像への指示を入力してください。');
    return { ...base, instruction };
  }

  let plan: unknown;
  try {
    plan = JSON.parse(input.value);
  } catch {
    throw new Error('構造化プランのJSONを確認してください。');
  }
  if (!plan || typeof plan !== 'object' || Array.isArray(plan)) {
    throw new Error('構造化プランにはJSONオブジェクトを入力してください。');
  }
  return { ...base, plan: plan as Record<string, unknown> };
}

function planText(plan: Record<string, unknown> | null): string {
  return JSON.stringify(plan ?? {}, null, 2);
}

function seconds(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}秒` : '未設定';
}

function sceneLabel(scene: CutDirectionScene): string {
  return scene.title?.trim() || scene.sceneId;
}

export function cutMatchesId(cut: Pick<CutDirectionCut, 'id' | 'cutId' | 'shots'>, itemId: string): boolean {
  return cut.id === itemId || cut.cutId === itemId || cut.shots.some((shot) => shot.id === itemId);
}

export function cutItemIdForDirectionSelection(
  cut: Pick<CutDirectionCut, 'id' | 'cutId' | 'shots'>,
  availableItemIds: ReadonlySet<string>,
): string | null {
  const firstVisibleShotId = cut.shots.find((shot) => availableItemIds.has(shot.id))?.id;
  if (firstVisibleShotId) return firstVisibleShotId;
  return [cut.id, cut.cutId].find((itemId) => availableItemIds.has(itemId)) ?? null;
}

function ActualImage({ runId, path, imageFileUrl, label }: {
  runId: string;
  path: string | null | undefined;
  imageFileUrl: Props['imageFileUrl'];
  label: string;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [path, runId]);
  if (!path || failed) return null;
  return (
    <img
      className="cutDirectionImage"
      src={imageFileUrl(runId, path)}
      alt={label}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}

function ShotCard({ shot, runId, imageFileUrl, videoFileUrl }: {
  shot: CutDirectionShot;
  runId: string;
  imageFileUrl: Props['imageFileUrl'];
  videoFileUrl: Props['videoFileUrl'];
}) {
  return (
    <Box className="cutDirectionShot">
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        <Typography className="cutDirectionShotName" fontWeight={800}>{shot.id}</Typography>
        <Chip size="small" label={`${seconds(shot.startSeconds)}から · ${seconds(shot.durationSeconds)}`} />
      </Stack>
      <Box className="cutDirectionShotFacts">
        <div><span>狙い</span><p>{shot.intent || '未記入'}</p></div>
        <div><span>フレーミング</span><p>{shot.framing || '未記入'}</p></div>
        <div><span>見える身体・対象</span><p>{shot.visibleSubjects.length ? shot.visibleSubjects.join('、') : '個別に映す人物・対象なし'}</p></div>
        <div><span>動き</span><p>{shot.motion || '未記入'}</p></div>
      </Box>
      {(shot.referencePaths.length > 0 || shot.imagePath || shot.videoPath) && (
        <Box className="cutDirectionReferences">
          {shot.referencePaths.length > 0 && <Typography variant="caption" color="text.secondary">参照画像</Typography>}
          <Box className="cutDirectionReferenceList">
            {shot.referencePaths.map((path) => (
              <a key={path} href={imageFileUrl(runId, path)} target="_blank" rel="noreferrer" title={path}>
                <ActualImage runId={runId} path={path} imageFileUrl={imageFileUrl} label={`参照画像 ${path}`} />
                <span>{path.split('/').pop()}</span>
              </a>
            ))}
            {shot.imagePath && (
              <a href={imageFileUrl(runId, shot.imagePath)} target="_blank" rel="noreferrer" title={shot.imagePath}>
                <ActualImage runId={runId} path={shot.imagePath} imageFileUrl={imageFileUrl} label={`${shot.id}の開始画像`} />
                <span>開始画像</span>
              </a>
            )}
            {shot.videoPath && (
              <video className="cutDirectionVideo" controls preload="none" src={videoFileUrl(runId, shot.videoPath)} aria-label={`${shot.id}の動画`} />
            )}
          </Box>
        </Box>
      )}
    </Box>
  );
}

export function CutDirectionPanel({
  runId,
  jsonFetch,
  imageFileUrl,
  videoFileUrl,
  selectedCutId = '',
  onSelectCut,
  onRefresh,
}: Props) {
  const [data, setData] = useState<CutDirectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [savedMessage, setSavedMessage] = useState('');
  const [sceneId, setSceneId] = useState('');
  const [cutId, setCutId] = useState('');
  const [editMode, setEditMode] = useState<EditMode>('plan');
  const [planDraft, setPlanDraft] = useState('{}');
  const [instructionDraft, setInstructionDraft] = useState('');
  const cutButtonRefs = useRef(new Map<string, HTMLButtonElement>());

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!runId) return;
    setLoading(true);
    setError('');
    try {
      const next = await jsonFetch<CutDirectionResponse>(
        `/api/image-gen/cut-direction?run_id=${encodeURIComponent(runId)}`,
        signal ? { signal } : undefined,
      );
      if (signal?.aborted) return;
      setData(next);
      setSceneId((current) => next.scenes.some((scene) => scene.sceneId === current)
        ? current
        : next.scenes[0]?.sceneId ?? '');
    } catch (cause) {
      if (!signal?.aborted) setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [jsonFetch, runId]);

  useEffect(() => {
    setData(null);
    setLoading(false);
    setSaving(false);
    setError('');
    setSavedMessage('');
    setSceneId('');
    setCutId('');
    setEditMode('plan');
    setPlanDraft('{}');
    setInstructionDraft('');
    if (!runId) return undefined;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, runId]);

  const selectedScene = useMemo(
    () => data?.scenes.find((scene) => scene.sceneId === sceneId) ?? data?.scenes[0] ?? null,
    [data, sceneId],
  );

  useEffect(() => {
    if (!data || !selectedCutId) return;
    for (const scene of data.scenes) {
      const match = scene.cuts.find((cut) => cutMatchesId(cut, selectedCutId));
      if (match) {
        setSceneId(scene.sceneId);
        setCutId(match.id);
        return;
      }
    }
  }, [data, selectedCutId]);

  useEffect(() => {
    if (!selectedScene) {
      setCutId('');
      return;
    }
    if (selectedScene.cuts.some((cut) => cut.id === cutId)) return;
    const next = selectedScene.cuts[0] ?? null;
    setCutId(next?.id ?? '');
  }, [cutId, selectedScene]);

  const selectedCut = selectedScene?.cuts.find((cut) => cut.id === cutId) ?? null;
  const selectedCutIndex = selectedScene?.cuts.findIndex((cut) => cut.id === selectedCut?.id) ?? -1;
  const stripCuts = selectedScene && selectedCutIndex >= 0
    ? selectedScene.cuts.slice(Math.max(0, selectedCutIndex - 1), selectedCutIndex + 2)
    : [];

  useEffect(() => {
    if (!selectedCut) return;
    setPlanDraft(planText(selectedCut.plan));
    setInstructionDraft('');
    setSavedMessage('');
    // Refresh the editor when the user changes cuts. A same-cut response after
    // saving must not replace the natural-language instruction they just sent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCut?.id]);

  const chooseCut = useCallback((scene: CutDirectionScene, cut: CutDirectionCut) => {
    setSceneId(scene.sceneId);
    setCutId(cut.id);
    setError('');
    setSavedMessage('');
    onSelectCut?.(scene, cut);
  }, [onSelectCut]);

  const changeScene = (nextSceneId: string) => {
    const nextScene = data?.scenes.find((scene) => scene.sceneId === nextSceneId);
    setSceneId(nextSceneId);
    const firstCut = nextScene?.cuts[0];
    if (nextScene && firstCut) chooseCut(nextScene, firstCut);
    else setCutId('');
  };

  const save = async () => {
    if (!data || !selectedCut || saving) return;
    let payload: CutDirectionSavePayload;
    try {
      payload = buildCutDirectionSavePayload({
        runId,
        itemId: selectedCut.id,
        expectedRevision: data.revision,
        mode: editMode,
        value: editMode === 'plan' ? planDraft : instructionDraft,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      return;
    }

    setSaving(true);
    setError('');
    setSavedMessage('');
    try {
      const updated = await jsonFetch<CutDirectionResponse>('/api/image-gen/cut-direction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      setData(updated);
      setSavedMessage('保存しました。ナレーションは保持されています。画像・動画の生成は行っていません。');
      await onRefresh?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  const handleCutKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, cut: CutDirectionCut) => {
    if (!selectedScene || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const index = selectedScene.cuts.findIndex((item) => item.id === cut.id);
    const nextIndex = event.key === 'Home' ? 0
      : event.key === 'End' ? selectedScene.cuts.length - 1
        : Math.max(0, Math.min(selectedScene.cuts.length - 1, index + (event.key === 'ArrowRight' ? 1 : -1)));
    const next = selectedScene.cuts[nextIndex];
    if (next) {
      chooseCut(selectedScene, next);
      window.requestAnimationFrame(() => cutButtonRefs.current.get(next.id)?.focus({ preventScroll: true }));
    }
  };

  return (
    <Box id="cut-direction-panel" component="section" className="cutDirectionPanel" aria-labelledby="cut-direction-title" tabIndex={-1}>
      <Stack className="cutDirectionHeader" direction="row" spacing={1.5} alignItems="center" useFlexGap flexWrap="wrap">
        <Box minWidth={0} flex={1}>
          <Typography id="cut-direction-title" variant="h6" fontWeight={800}>カットの映像設計</Typography>
          <Typography variant="body2" color="text.secondary">音声の長さを保ったまま、カット内のショットを見て調整します。</Typography>
        </Box>
        {selectedCut && <Chip size="small" label={selectedCut.source === 'shot_direction_v1' ? 'ショット設計' : '既存データ'} />}
        <Button
          size="small"
          startIcon={<RefreshIcon />}
          onClick={() => void load()}
          disabled={!runId || loading || saving}
          aria-label="カット映像設計を再読込"
        >再読込</Button>
      </Stack>

      {loading && <LinearProgress className="cutDirectionProgress" aria-label="カット映像設計を読み込み中" />}
      {error && <Alert severity="error" className="cutDirectionAlert" action={
        !data ? <Button color="inherit" size="small" onClick={() => void load()} disabled={loading}>再試行</Button> : undefined
      }>{error}</Alert>}
      {savedMessage && <Alert severity="success" className="cutDirectionAlert">{savedMessage}</Alert>}
      {runId && <VideoPreparationPanel runId={runId} jsonFetch={jsonFetch} onRefresh={onRefresh} />}
      {!runId && <Typography className="cutDirectionEmpty" color="text.secondary">作品を選択してください。</Typography>}
      {runId && !loading && !error && data && data.scenes.length === 0 && (
        <Typography className="cutDirectionEmpty" color="text.secondary">この作品には映像設計データがありません。</Typography>
      )}
      {data && data.scenes.length > 0 && (
        <>
          <FormControl size="small" className="cutDirectionSceneSelect">
            <InputLabel id="cut-direction-scene-label">シーン</InputLabel>
            <Select
              labelId="cut-direction-scene-label"
              label="シーン"
              value={selectedScene?.sceneId ?? ''}
              onChange={(event) => changeScene(event.target.value)}
              disabled={loading || saving}
            >
              {data.scenes.map((scene) => (
                <MenuItem key={scene.sceneId} value={scene.sceneId}>{sceneLabel(scene)} · {scene.cuts.length} cut</MenuItem>
              ))}
            </Select>
          </FormControl>

          {selectedScene && selectedScene.cuts.length === 0 && (
            <Typography className="cutDirectionEmpty" color="text.secondary">このシーンにcutはありません。</Typography>
          )}
          {selectedScene && selectedCut && (
            <>
              <Box className="cutDirectionStrip" aria-label={`${sceneLabel(selectedScene)}の前後cut`}>
                {stripCuts.map((cut) => {
                  const active = cut.id === selectedCut.id;
                  return (
                    <button
                      key={cut.id}
                      type="button"
                      className={`cutDirectionCut${active ? ' isSelected' : ''}`}
                      aria-pressed={active}
                      aria-label={`${cut.cutId} ${active ? '選択中' : 'cutを選択'}`}
                      onClick={() => chooseCut(selectedScene, cut)}
                      onKeyDown={(event) => handleCutKeyDown(event, cut)}
                      ref={(element) => {
                        if (element) cutButtonRefs.current.set(cut.id, element);
                        else cutButtonRefs.current.delete(cut.id);
                      }}
                      disabled={loading || saving}
                    >
                      <Box className="cutDirectionCutImageFrame">
                        <ActualImage runId={runId} path={cut.thumbnailPath} imageFileUrl={imageFileUrl} label={`${cut.cutId}の既存画像`} />
                        {!cut.thumbnailPath && <span>画像なし</span>}
                      </Box>
                      <span className="cutDirectionCutTitle">{cut.cutId}</span>
                      <span className="cutDirectionCutIntent">{cut.intent || '映像の狙いは未記入'}</span>
                      <span className="cutDirectionCutMeta">映像 {seconds(cut.durationSeconds)} · 音声 {seconds(cut.narrationDurationSeconds)}</span>
                      <span className="cutDirectionCutMeta">{cut.shots.length} shots</span>
                    </button>
                  );
                })}
              </Box>

              <Box className="cutDirectionShotSection">
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="baseline">
                  <Typography variant="subtitle1" fontWeight={800}>{selectedCut.cutId}のショット</Typography>
                  <Typography variant="caption" color="text.secondary">
                    映像 {seconds(selectedCut.durationSeconds)} · ナレーション {seconds(selectedCut.narrationDurationSeconds)}
                  </Typography>
                </Stack>
                {selectedCut.shots.length ? (
                  <Box className="cutDirectionShotList">
                    {selectedCut.shots.map((shot) => (
                      <ShotCard key={shot.id} shot={shot} runId={runId} imageFileUrl={imageFileUrl} videoFileUrl={videoFileUrl} />
                    ))}
                  </Box>
                ) : (
                  <Typography variant="body2" color="text.secondary">このcutにはショットがまだありません。</Typography>
                )}
              </Box>

              <Box className="cutDirectionEditor">
                <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                  <Typography variant="subtitle1" fontWeight={800}>映像設計を編集</Typography>
                  <Typography variant="caption" color="text.secondary">保存で映像設計だけを更新します。生成や承認は行いません。</Typography>
                </Stack>
                <RadioGroup
                  row
                  className="cutDirectionMode"
                  value={editMode}
                  onChange={(event) => { setEditMode(event.target.value as EditMode); setError(''); setSavedMessage(''); }}
                  aria-label="編集方法"
                >
                  <FormControlLabel value="plan" control={<Radio size="small" />} label="構造化プラン" />
                  <FormControlLabel value="instruction" control={<Radio size="small" />} label="自然文の指示" />
                </RadioGroup>
                {editMode === 'plan' ? (
                  <TextField
                    className="cutDirectionInput"
                    label="構造化プラン（JSON）"
                    value={planDraft}
                    onChange={(event) => { setPlanDraft(event.target.value); setError(''); setSavedMessage(''); }}
                    multiline
                    minRows={5}
                    maxRows={12}
                    spellCheck={false}
                    disabled={saving}
                    inputProps={{ 'aria-label': '構造化プランJSON' }}
                  />
                ) : (
                  <TextField
                    className="cutDirectionInput"
                    label="このcutへの映像指示"
                    value={instructionDraft}
                    onChange={(event) => { setInstructionDraft(event.target.value); setError(''); setSavedMessage(''); }}
                    multiline
                    minRows={4}
                    maxRows={8}
                    placeholder="例：人物の顔を見せず、手元と道具の接触に寄った構図にする。"
                    disabled={saving}
                    inputProps={{ 'aria-label': '自然文の映像指示' }}
                  />
                )}
                <Button
                  variant="contained"
                  startIcon={<SaveIcon />}
                  onClick={() => void save()}
                  disabled={saving || loading || (editMode === 'instruction' && !instructionDraft.trim())}
                >{saving ? '保存中' : '映像設計を保存'}</Button>
              </Box>
            </>
          )}
        </>
      )}
    </Box>
  );
}
