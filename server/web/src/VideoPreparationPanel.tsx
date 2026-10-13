import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopCircleOutlinedIcon from '@mui/icons-material/StopCircleOutlined';
import './videoPreparationPanel.css';

export type VideoPreparationScene = {
  sceneId: string;
  status: string;
  reason?: string;
  changedCuts?: string[];
  imageCount?: number;
};

export type VideoPreparationDto = {
  runId: string;
  enabled: boolean;
  operationId: string | null;
  status: 'idle' | 'running' | 'completed' | 'needs_input' | 'failed';
  scenes: VideoPreparationScene[];
  budget?: { reservedCostUsd: number; imageCount: number };
  error?: string;
};

type VideoPreparationRequestBody = {
  run_id: string;
  max_image_generations: number;
  max_cost_usd: number | null;
  fixed_image_paths: string[];
  target_video_model?: 'higgsfield_kling_standard' | null;
};

type JsonFetch = <T>(input: RequestInfo, init?: RequestInit) => Promise<T>;

type Props = {
  runId: string;
  jsonFetch: JsonFetch;
  onRefresh?: () => void | Promise<void>;
};

type RequestBodyInput = {
  runId: string;
  maxImageGenerations: number;
  maxCostUsd: number | null;
  fixedImagePathsText: string;
  targetVideoModel?: 'higgsfield_kling_standard' | null;
};

const STATUS_LABELS: Record<VideoPreparationDto['status'], string> = {
  idle: '未開始',
  running: '実行中',
  completed: '準備完了',
  needs_input: '確認が必要',
  failed: '失敗',
};

const SCENE_STATUS_LABELS: Record<string, string> = {
  idle: '待機中',
  pending: '待機中',
  running: '処理中',
  unchanged: '変更なし',
  revised: '調整あり',
  needs_input: '確認が必要',
  completed: '完了',
  failed: '失敗',
};

function statusColor(status: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  if (status === 'running') return 'info';
  if (status === 'completed' || status === 'unchanged' || status === 'revised') return 'success';
  if (status === 'needs_input') return 'warning';
  if (status === 'failed') return 'error';
  return 'default';
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status as VideoPreparationDto['status']]
    ?? SCENE_STATUS_LABELS[status]
    ?? '状態を確認中';
}

function usd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 4,
  }).format(value);
}

export function VideoPreparationSummary({ data }: { data: VideoPreparationDto }) {
  return (
    <Box className="videoPreparationSummary" aria-live="polite">
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
        <Typography variant="subtitle2" fontWeight={800}>シーンごとの準備状況</Typography>
        <Chip size="small" color={statusColor(data.status)} label={statusLabel(data.status)} />
      </Stack>
      {!data.enabled && (
        <Typography variant="caption" color="text.secondary">準備はまだ有効になっていません。開始操作で有効にします。</Typography>
      )}
      {data.budget && (
        <Typography className="videoPreparationBudget" variant="caption" color="text.secondary">
          予約済み: 画像 {data.budget.imageCount}枚 · {usd(data.budget.reservedCostUsd)}
        </Typography>
      )}
      {data.error && <Alert severity="warning" className="videoPreparationMessage">{data.error}</Alert>}
      {data.scenes.length > 0 ? (
        <Box className="videoPreparationSceneList">
          {data.scenes.map((scene) => (
            <Box className="videoPreparationScene" key={scene.sceneId}>
              <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                <Typography variant="body2" fontWeight={700}>シーン {scene.sceneId}</Typography>
                <Chip size="small" color={statusColor(scene.status)} label={statusLabel(scene.status)} />
                {scene.changedCuts && scene.changedCuts.length > 0 && (
                  <Typography variant="caption" color="text.secondary">変更対象 {scene.changedCuts.length} cut</Typography>
                )}
                {typeof scene.imageCount === 'number' && (
                  <Typography variant="caption" color="text.secondary">画像 {scene.imageCount}枚</Typography>
                )}
              </Stack>
              {scene.reason && <Typography className="videoPreparationReason" variant="body2" color="text.secondary">{scene.reason}</Typography>}
            </Box>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">準備結果はまだありません。</Typography>
      )}
    </Box>
  );
}

export function buildVideoPreparationRequestBody(input: RequestBodyInput): VideoPreparationRequestBody {
  if (!Number.isInteger(input.maxImageGenerations) || input.maxImageGenerations < 0) {
    throw new Error('追加画像の上限枚数には0以上の整数を入力してください。');
  }
  if (input.maxCostUsd !== null && (!Number.isFinite(input.maxCostUsd) || input.maxCostUsd < 0)) {
    throw new Error('費用上限には0以上の金額を入力してください。');
  }
  const body: VideoPreparationRequestBody = {
    run_id: input.runId,
    max_image_generations: input.maxImageGenerations,
    max_cost_usd: input.maxCostUsd,
    fixed_image_paths: input.fixedImagePathsText.split(/\r?\n/).map((path) => path.trim()).filter(Boolean),
  };
  if (input.targetVideoModel !== undefined) body.target_video_model = input.targetVideoModel;
  return body;
}

export function canCancelVideoPreparation(status: VideoPreparationDto['status'] | null | undefined): boolean {
  return status === 'running';
}

export function buildVideoPreparationCancelBody(runId: string): { run_id: string } {
  return { run_id: runId };
}

export function VideoPreparationPanel({ runId, jsonFetch, onRefresh }: Props) {
  const [data, setData] = useState<VideoPreparationDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState('');
  const [reloadToken, setReloadToken] = useState(0);
  const [maxImageGenerations, setMaxImageGenerations] = useState('1');
  const [maxCostUsd, setMaxCostUsd] = useState('');
  const [fixedImagePathsText, setFixedImagePathsText] = useState('');
  const [targetVideoModel, setTargetVideoModel] = useState<'higgsfield_kling_standard' | null>(null);
  const lastRefreshOperation = useRef<string | null>(null);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  const readStatus = useCallback(async (signal?: AbortSignal): Promise<VideoPreparationDto> => {
    const next = await jsonFetch<VideoPreparationDto>(
      `/api/image-gen/video-preparation?run_id=${encodeURIComponent(runId)}`,
      signal ? { signal } : undefined,
    );
    if (!signal?.aborted) {
      setData(next);
      setError('');
    }
    return next;
  }, [jsonFetch, runId]);

  useEffect(() => {
    if (!runId) {
      setData(null);
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    setData(null);
    setError('');
    setLoading(true);
    void readStatus(controller.signal).catch((cause) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [readStatus, reloadToken, runId]);

  useEffect(() => {
    if (!runId || !canCancelVideoPreparation(data?.status) || cancelling) return undefined;
    const controller = new AbortController();
    let timeout: number | undefined;
    const poll = async () => {
      try {
        await readStatus(controller.signal);
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
      }
      if (!controller.signal.aborted) timeout = window.setTimeout(poll, 1500);
    };
    timeout = window.setTimeout(poll, 1500);
    return () => {
      controller.abort();
      if (timeout !== undefined) window.clearTimeout(timeout);
    };
  }, [cancelling, data?.operationId, data?.status, readStatus, runId]);

  useEffect(() => {
    if (data?.status !== 'completed') return;
    const operationKey = data.operationId ?? `completed:${runId}`;
    if (lastRefreshOperation.current === operationKey) return;
    lastRefreshOperation.current = operationKey;
    void Promise.resolve(onRefreshRef.current?.()).catch((cause) => {
      setError(cause instanceof Error ? cause.message : String(cause));
    });
  }, [data?.operationId, data?.status, runId]);

  const submit = async () => {
    if (!runId || submitting) return;
    let body: VideoPreparationRequestBody;
    try {
      body = buildVideoPreparationRequestBody({
        runId,
        maxImageGenerations: Number(maxImageGenerations),
        maxCostUsd: maxCostUsd.trim() ? Number(maxCostUsd) : null,
        fixedImagePathsText,
        targetVideoModel,
      });
      if (body.max_cost_usd === null) throw new Error('費用上限を入力してください。');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const next = await jsonFetch<VideoPreparationDto>('/api/image-gen/video-preparation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      setData(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = async () => {
    if (!runId || !canCancelVideoPreparation(data?.status) || cancelling) return;
    setCancelling(true);
    setError('');
    try {
      const next = await jsonFetch<VideoPreparationDto>('/api/image-gen/video-preparation/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildVideoPreparationCancelBody(runId)),
      });
      setData(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setCancelling(false);
    }
  };

  const parsedImageCap = Number(maxImageGenerations);
  const parsedCostCap = Number(maxCostUsd);
  const validCaps = maxImageGenerations.trim().length > 0
    && Number.isInteger(parsedImageCap) && parsedImageCap >= 0
    && maxCostUsd.trim().length > 0 && Number.isFinite(parsedCostCap) && parsedCostCap >= 0;
  const busy = loading || submitting || cancelling || data?.status === 'running';

  return (
    <Box className="videoPreparationPanel" component="section" aria-labelledby="video-preparation-title">
      <Stack className="videoPreparationHeader" direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
        <Box minWidth={0} flex={1}>
          <Typography id="video-preparation-title" variant="subtitle1" fontWeight={800}>動画生成前の全シーン準備</Typography>
          <Typography variant="body2" color="text.secondary">
            開始操作で準備を明示的に有効にします。既存画像を固定する場合は、作品内の相対パスを指定してください。
          </Typography>
          <Typography variant="caption" color="text.secondary">
            選択した動画モデルは全シーンに適用されます。画像も修正する演出調整は、現在Higgsfield Kling 3.0 Standardに対応しています。
          </Typography>
        </Box>
        <Button
          size="small"
          startIcon={<RefreshIcon />}
          onClick={() => setReloadToken((current) => current + 1)}
          disabled={!runId || loading || submitting}
          aria-label="動画準備の状態を再読込"
        >再読込</Button>
      </Stack>
      {loading && <LinearProgress aria-label="動画準備の状態を読み込み中" />}
      {error && <Alert severity="error" className="videoPreparationMessage">{error}</Alert>}
      {data && <VideoPreparationSummary data={data} />}
      {data?.status === 'needs_input' && !data.error && (
        <Alert severity="warning" className="videoPreparationMessage">表示された理由を確認し、必要な設定を入力してから再度開始してください。</Alert>
      )}
      {canCancelVideoPreparation(data?.status) && (
        <Box className="videoPreparationRunning">
          <Typography variant="body2" color="text.secondary">中断後は保存した処理履歴から再開できます。</Typography>
          <Button
            variant="outlined"
            color="warning"
            startIcon={<StopCircleOutlinedIcon />}
            onClick={() => void cancel()}
            disabled={cancelling}
          >{cancelling ? '中断中' : '処理を中断'}</Button>
        </Box>
      )}
      <Box className="videoPreparationControls">
        <TextField
          size="small"
          label="追加画像の上限枚数"
          type="number"
          value={maxImageGenerations}
          onChange={(event) => setMaxImageGenerations(event.target.value)}
          inputProps={{ min: 0, step: 1 }}
          disabled={busy}
        />
        <TextField
          size="small"
          select
          label="動画モデル"
          value={targetVideoModel ?? 'current'}
          onChange={(event) => setTargetVideoModel(
            event.target.value === 'higgsfield_kling_standard' ? 'higgsfield_kling_standard' : null,
          )}
          helperText="既定は現在の設定を保持します。"
          disabled={busy}
        >
          <MenuItem value="current">現在の設定を保持</MenuItem>
          <MenuItem value="higgsfield_kling_standard">Higgsfield Kling 3.0 Standardを使う</MenuItem>
        </TextField>
        <TextField
          size="small"
          label="費用上限（USD）"
          type="number"
          value={maxCostUsd}
          onChange={(event) => setMaxCostUsd(event.target.value)}
          inputProps={{ min: 0, step: 0.01 }}
          helperText="価格見積はサーバー設定を使います。未設定なら準備は確認待ちになります。"
          disabled={busy}
        />
        <TextField
          className="videoPreparationFixedPaths"
          size="small"
          label="固定する画像のパス（任意）"
          value={fixedImagePathsText}
          onChange={(event) => setFixedImagePathsText(event.target.value)}
          multiline
          minRows={2}
          maxRows={5}
          placeholder={'images/scene01_start.png\nassets/character/reference.webp'}
          helperText="作品内の相対パスを1行に1つ入力します。空欄では自動選択されません。"
          disabled={busy}
        />
        <Button
          variant="contained"
          startIcon={<PlayArrowIcon />}
          onClick={() => void submit()}
          disabled={!runId || !data || busy || !validCaps}
        >
          {submitting ? '開始中' : data?.status === 'completed' ? '全シーンを再準備' : '全シーンの準備を開始'}
        </Button>
      </Box>
    </Box>
  );
}
