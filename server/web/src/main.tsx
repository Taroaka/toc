import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AppBar,
  Autocomplete,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CssBaseline,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Slider,
  Stack,
  Tab,
  Tabs,
  TextField,
  ThemeProvider,
  Tooltip,
  Typography,
  createTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ArchiveIcon from '@mui/icons-material/Archive';
import ChatIcon from '@mui/icons-material/Chat';
import DownloadIcon from '@mui/icons-material/Download';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import ImageIcon from '@mui/icons-material/Image';
import MovieCreationIcon from '@mui/icons-material/MovieCreation';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import SendIcon from '@mui/icons-material/Send';
import SaveIcon from '@mui/icons-material/Save';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import RefreshIcon from '@mui/icons-material/Refresh';
import SettingsIcon from '@mui/icons-material/Settings';
import { GlassDock, GlassPanel, GlassStatusRim, GlassSurface } from './components';
import './styles.css';

type RunFolder = {
  id: string;
  name: string;
  path: string;
  hasAssetRequests: boolean;
  hasSceneRequests: boolean;
};

type ImageRequestItem = {
  id: string;
  kind: 'asset' | 'scene';
  assetType: string | null;
  tool: string | null;
  output: string | null;
  prompt: string;
  references: string[];
  referenceCount: number;
  executionLane: string;
  generationStatus: string | null;
  existingImage: string | null;
  candidates?: Candidate[];
};

type ReferenceOption = {
  path: string;
  label: string;
};

type Candidate = {
  index: number;
  status: string;
  path: string | null;
  error?: string;
  revisedPrompt?: string | null;
  mtimeMs?: number;
};

type EditableItem = ImageRequestItem & {
  draftPrompt: string;
  selectedReferences: ReferenceOption[];
  candidates: Candidate[];
  selectedCandidatePath: string | null;
  generating: boolean;
  promptGenerating?: boolean;
  videoCandidates: Candidate[];
  videoGenerating: boolean;
  videoDraftPrompt: string;
  videoQuality: string;
  videoAspectRatio: string;
  videoDurationSec: number;
  videoFirstReferencePath: string | null;
  videoLastReferencePath: string | null;
  videoReferencePaths: string[];
  videoTool: string;
  sceneKey: string | null;
  sceneLabel: string;
  narrationText: string;
  narrationTtsText: string;
  narrationOutput: string | null;
  narrationTool: string;
  narrationDurationSec: number | null;
  narrationExists: boolean;
  narrationGenerating: boolean;
  renderVideoPath: string | null;
  renderVideoExists: boolean;
  renderVideoDurationSec: number;
  renderNarrationPath: string | null;
  renderNarrationOffsetSec: number;
};

type ViewKind = 'asset' | 'scene';
type WorkspaceMode = 'image' | 'narration' | 'video' | 'render';
type AssetFilter = 'chara' | 'obj' | 'location' | 'asset';
type AssetCategory = 'chara' | 'obj' | 'location' | 'asset';
type AssetCreateType = 'character' | 'object' | 'location';
type InsertStatus = 'idle' | 'running' | 'success' | 'error';
type SettingsTarget = 'character' | 'item' | 'location' | 'scene';

type PromptSettingResponse = {
  target: SettingsTarget;
  label: string;
  path: string;
  content: string;
};

type RegeneratedPrompt = {
  itemId: string;
  prompt: string;
};

type RegeneratePromptsResponse = {
  status: string;
  prompts: RegeneratedPrompt[];
  updated: string[];
  missing: string[];
};

type FrontendReviewResponse = {
  status: string;
  path?: string;
  progress?: RunProgress;
};

type ProgressResponse = {
  progress: RunProgress;
};

type InsertCutResponse = {
  status: string;
  selector: string;
  imageOutput: string;
  videoOutput: string;
  audioOutput: string;
  progress?: RunProgress;
};

type AssetCreateResponse = {
  status: string;
  item: ImageRequestItem;
  references: ReferenceOption[];
  progress?: RunProgress;
};

type VideoGenerateItemPayload = {
  item_id: string;
  prompt: string;
  first_reference: string | null;
  last_reference: string | null;
  references: string[];
  quality: string;
  aspect_ratio: string;
  duration_seconds: number;
  tool: string;
  candidate_count: number;
};

type NarrationManifestItem = {
  itemId: string;
  sceneId: string | null;
  cutIndex: number | null;
  imageOutput: string | null;
  videoOutput: string | null;
  selectedVideoPath: string | null;
  videoExists: boolean;
  videoDurationSeconds: number | null;
  configuredVideoDurationSeconds: number;
  videoPrompt: string;
  videoTool: string;
  videoQuality: string;
  videoAspectRatio: string;
  videoFirstReference: string;
  videoLastReference: string;
  videoReferences: string[];
  narrationText: string;
  narrationTtsText: string;
  narrationOutput: string | null;
  narrationTool: string;
  narrationExists: boolean;
  narrationDurationSeconds: number | null;
  renderNarrationOffsetSeconds: number;
  prompt: string;
};

type NarrationGenerateResponse = {
  status: string;
  item: {
    itemId: string;
    status: string;
    path: string | null;
    durationSeconds: number | null;
    error?: string;
  };
  progress?: RunProgress;
};

type BulkNarrationGenerateResponse = {
  status: string;
  results: NarrationGenerateResponse['item'][];
  progress?: RunProgress;
};

type RenderActionResponse = {
  status: string;
  output?: string;
  finalOutput?: string;
  clipList?: string;
  narrationList?: string;
  warnings?: string[];
  progress?: RunProgress;
};

type RunStage = {
  code: string;
  label: string;
  state: string;
};

type RunSlot = {
  code: string;
  stage: string;
  requirement: string;
  purpose: string;
  plannedArtifacts: string[];
  state: string;
};

type RunProgress = {
  topic: string;
  status: string;
  runtimeStage: string;
  reviewPolicy: string;
  pendingGates: string[];
  currentStage: RunStage | null;
  stages: RunStage[];
  slots: RunSlot[];
  doneCount: number;
  totalCount: number;
  percent: number;
};

type CreateRunJob = {
  jobId: string;
  runId: string;
  path: string;
  status: 'running' | 'completed' | 'failed';
  title: string;
  message?: string | null;
  error?: string | null;
  errorCode?: string | null;
};

type CandidatesResponse = {
  itemId: string;
  candidates: Candidate[];
  durationSeconds?: number;
  minDurationSeconds?: number | null;
};

type EnlargedImage = {
  itemId: string;
  label: string;
  path: string;
  src: string;
};

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0e1113',
      paper: '#171b1f',
    },
    primary: {
      main: '#ffb347',
    },
    secondary: {
      main: '#f6d365',
    },
    divider: 'rgba(255,255,255,0.12)',
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: '"IBM Plex Sans", "Noto Sans JP", "Helvetica Neue", sans-serif',
    h6: {
      fontWeight: 800,
      letterSpacing: 0,
    },
    button: {
      textTransform: 'none',
      fontWeight: 800,
    },
  },
});

function fileUrl(runId: string, path: string): string {
  return `/api/image-gen/file?run_id=${encodeURIComponent(runId)}&path=${encodeURIComponent(path)}`;
}

function videoFileUrl(runId: string, path: string): string {
  return `/api/image-gen/video-file?run_id=${encodeURIComponent(runId)}&path=${encodeURIComponent(path)}`;
}

function audioFileUrl(runId: string, path: string): string {
  return `/api/image-gen/audio-file?run_id=${encodeURIComponent(runId)}&path=${encodeURIComponent(path)}`;
}

async function jsonFetch<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function defaultVideoPrompt(item: ImageRequestItem): string {
  return [
    '静止画の人物・構図・光を保ったまま、自然なカメラ移動と小さな環境変化だけで動かす。',
    '',
    'シーン説明:',
    item.prompt || 'このcutの静止画を動画化する。',
  ].join('\n');
}

function inferSceneKey(itemId: string, sceneId?: string | null): string | null {
  const normalizedSceneId = (sceneId || '').trim();
  if (normalizedSceneId) return `scene${normalizedSceneId}`;
  const match = itemId.match(/^scene([^_]+)/);
  return match?.[1] ? `scene${match[1]}` : null;
}

function sceneLabelFromKey(sceneKey: string | null): string {
  if (!sceneKey) return 'scene';
  return sceneKey.replace(/^scene/, 'scene ');
}

function toEditableItems(items: ImageRequestItem[], refs: ReferenceOption[], narrationById?: Map<string, NarrationManifestItem>): EditableItem[] {
  const byPath = new Map(refs.map((ref) => [ref.path, ref]));
  return items.map((item) => {
    const selectedReferences = item.references.map((ref) => byPath.get(ref)).filter(Boolean) as ReferenceOption[];
    const narration = narrationById?.get(item.id);
    const sceneKey = inferSceneKey(item.id, narration?.sceneId);
    const narrationMinDuration = Math.max(1, Math.ceil(narration?.narrationDurationSeconds || 0));
    const configuredVideoDuration = Math.max(narration?.configuredVideoDurationSeconds || 8, narrationMinDuration);
    const videoPrompt = narration?.videoPrompt?.trim() || defaultVideoPrompt(item);
    return {
      ...item,
      draftPrompt: item.prompt,
      selectedReferences,
      candidates: item.candidates || [],
      selectedCandidatePath: item.candidates?.find((candidate) => candidate.path)?.path ?? null,
      generating: false,
      promptGenerating: false,
      videoCandidates: [],
      videoGenerating: false,
      videoDraftPrompt: videoPrompt,
      videoQuality: narration?.videoQuality || '1080p',
      videoAspectRatio: narration?.videoAspectRatio || '16:9',
      videoDurationSec: configuredVideoDuration,
      videoFirstReferencePath: narration?.videoFirstReference || item.existingImage || selectedReferences[0]?.path || null,
      videoLastReferencePath: narration?.videoLastReference || null,
      videoReferencePaths: narration?.videoReferences?.length ? narration.videoReferences : selectedReferences.map((ref) => ref.path),
      videoTool: narration?.videoTool || 'kling_3_0',
      sceneKey,
      sceneLabel: sceneLabelFromKey(sceneKey),
      narrationText: narration?.narrationText || '',
      narrationTtsText: narration?.narrationTtsText || narration?.narrationText || '',
      narrationOutput: narration?.narrationOutput || null,
      narrationTool: narration?.narrationTool || 'elevenlabs',
      narrationDurationSec: narration?.narrationDurationSeconds ?? null,
      narrationExists: Boolean(narration?.narrationExists),
      narrationGenerating: false,
      renderVideoPath: narration?.selectedVideoPath || narration?.videoOutput || null,
      renderVideoExists: Boolean(narration?.videoExists),
      renderVideoDurationSec: configuredVideoDuration,
      renderNarrationPath: narration?.narrationOutput || null,
      renderNarrationOffsetSec: narration?.renderNarrationOffsetSeconds ?? 0,
    };
  });
}

function mergeLoadedItemsWithInflight(prev: EditableItem[], next: EditableItem[]): EditableItem[] {
  const previousById = new Map(prev.map((item) => [item.id, item]));
  const merged = next.map((item) => {
    const previous = previousById.get(item.id);
    if (!previous) return item;
    if (!previous.generating && !previous.promptGenerating && !previous.videoGenerating && !previous.narrationGenerating) return item;
    return {
      ...item,
      generating: previous.generating,
      promptGenerating: previous.promptGenerating,
      candidates: previous.generating ? previous.candidates : item.candidates,
      selectedCandidatePath: previous.selectedCandidatePath ?? item.selectedCandidatePath,
      videoGenerating: previous.videoGenerating,
      videoCandidates: previous.videoGenerating ? previous.videoCandidates : item.videoCandidates,
      renderVideoPath: previous.renderVideoPath ?? item.renderVideoPath,
      renderVideoExists: previous.renderVideoExists || item.renderVideoExists,
      narrationGenerating: previous.narrationGenerating,
      narrationExists: previous.narrationExists || item.narrationExists,
      narrationOutput: previous.narrationOutput ?? item.narrationOutput,
      renderNarrationPath: previous.renderNarrationPath ?? item.renderNarrationPath,
    };
  });
  const nextIds = new Set(next.map((item) => item.id));
  const carryOver = prev.filter(
    (item) => !nextIds.has(item.id) && (item.generating || item.promptGenerating || item.videoGenerating || item.narrationGenerating),
  );
  return carryOver.length ? [...merged, ...carryOver] : merged;
}

function candidateErrorMessage(error: unknown): string {
  const text = String(error);
  if (text.includes('savedPath')) return 'savedPath missing';
  if (text.includes('reference')) return 'reference error';
  if (text.includes('disabled')) return 'app-server disabled';
  if (text.includes('timed out')) return 'generation timed out';
  return 'generation failed';
}

function candidateDisplayMessage(candidate: Candidate, generating: boolean): string {
  if (candidate.error) {
    if (candidate.error.includes('savedPath')) return '画像保存に失敗';
    if (candidate.error.includes('disabled')) return 'app-server停止中';
    if (candidate.error.includes('reference')) return '参照画像エラー';
    if (candidate.error.includes('timed out')) return '生成タイムアウト';
    return '生成失敗';
  }
  return generating ? '生成中' : '待機中';
}

function videoCandidateDisplayMessage(candidate: Candidate, generating: boolean): string {
  if (candidate.error) {
    if (candidate.error.includes('credential') || candidate.error.includes('Missing')) return '認証設定エラー';
    if (candidate.error.includes('reference')) return '参照画像エラー';
    if (candidate.error.includes('timed out')) return '生成タイムアウト';
    return '動画生成失敗';
  }
  return generating ? '動画生成中' : '待機中';
}

function executionLaneLabel(lane: string): string {
  const labels: Record<string, string> = {
    bootstrap_builtin: '参照なし生成',
    existing_asset: '既存素材',
    standard: '参照あり生成',
  };
  return labels[lane] ?? '生成設定あり';
}

function viewLabel(view: ViewKind): string {
  return view === 'scene' ? 'シーン' : '素材';
}

function workspaceModeTitle(mode: WorkspaceMode): string {
  if (mode === 'narration') return 'ナレーション生成と確認';
  if (mode === 'video') return '動画候補の生成';
  if (mode === 'render') return '最終レンダー入力';
  return '画像候補の比較と採用';
}

function workspaceModeLabel(mode: WorkspaceMode): string {
  if (mode === 'narration') return '音声 / シーン';
  if (mode === 'video') return '動画 / シーン';
  if (mode === 'render') return '最終 / シーン';
  return '画像';
}

function assetFilterLabel(filter: AssetFilter): string {
  return { chara: 'キャラクター', obj: 'アイテム', location: '場所', asset: '全素材' }[filter];
}

function assetCreateTypeLabel(type: AssetCreateType): string {
  return { character: 'キャラクター', object: 'アイテム', location: '場所' }[type];
}

function assetCreateDesignPrompt(type: AssetCreateType, title: string): string {
  const name = title.trim() || '未入力';
  if (type === 'character') {
    return [
      '[作成対象]',
      `${name} のキャラクター参照画像`,
      '',
      '[設計方針]',
      '顔、髪型、衣装、年齢感、体格、シルエットを固定する。',
      '後続cutで同一人物として読み取れる continuity anchor にする。',
      '',
      '[禁止]',
      '文字、ロゴ、別人物化、過度な表情演技、背景に依存した説明。',
    ].join('\n');
  }
  if (type === 'object') {
    return [
      '[作成対象]',
      `${name} のアイテム参照画像`,
      '',
      '[設計方針]',
      'silhouette、材質、装飾、縮尺感、工芸の痕跡、物語上の役割を固定する。',
      '単体で見ても後続cutの小道具として使える asset bible にする。',
      '',
      '[禁止]',
      '文字、ロゴ、単なる装飾化、用途が分からない抽象物。',
    ].join('\n');
  }
  return [
    '[作成対象]',
    `${name} の場所参照画像`,
    '',
    '[設計方針]',
    'spatial identity、主要構造、光環境、場所固有の空気を固定する。',
    '人物を置かず、後続cutの背景 continuity anchor として成立させる。',
    '',
    '[禁止]',
    '人物、群衆、看板、字幕、読める文字、ロゴ。',
  ].join('\n');
}

function settingsTargetLabel(target: SettingsTarget): string {
  return { character: 'キャラクター', item: 'アイテム', location: '場所', scene: 'シーン' }[target];
}

function targetToMainView(target: SettingsTarget): { viewKind: ViewKind; assetFilter: AssetFilter } {
  if (target === 'scene') return { viewKind: 'scene', assetFilter: 'asset' };
  if (target === 'character') return { viewKind: 'asset', assetFilter: 'chara' };
  if (target === 'item') return { viewKind: 'asset', assetFilter: 'obj' };
  return { viewKind: 'asset', assetFilter: 'location' };
}

function assetCategory(item: EditableItem): AssetCategory {
  const assetType = (item.assetType || '').toLowerCase();
  const output = (item.output || '').toLowerCase();
  if (assetType.includes('character') || output.startsWith('assets/characters/')) return 'chara';
  if (assetType.includes('object') || output.startsWith('assets/objects/')) return 'obj';
  if (assetType.includes('location') || output.startsWith('assets/locations/') || output.startsWith('assets/location/')) return 'location';
  return 'asset';
}

function assetCategoryRank(category: AssetCategory): number {
  return { chara: 0, obj: 1, location: 2, asset: 3 }[category];
}

function itemMatchesAssetFilter(item: EditableItem, filter: AssetFilter): boolean {
  if (filter === 'asset') return item.kind === 'asset';
  return assetCategory(item) === filter;
}

function sortAssetItems(items: EditableItem[]): EditableItem[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const rankDiff = assetCategoryRank(assetCategory(a.item)) - assetCategoryRank(assetCategory(b.item));
      return rankDiff || a.index - b.index;
    })
    .map(({ item }) => item);
}

function isSceneCutItem(item: EditableItem): boolean {
  return item.kind === 'scene' && Boolean(item.output);
}

function stageStateLabel(state: string): string {
  const labels: Record<string, string> = {
    always_available: '入口',
    done: '完了',
    not_started: '未着手',
    pending: '待機',
    in_progress: '進行中',
    blocked: '停止',
    awaiting_approval: '承認待ち',
    failed: '失敗',
    skipped: 'スキップ',
  };
  return labels[state] ?? (state || '不明');
}

const stageLabelJa: Record<string, string> = {
  p000: '入口',
  p100: 'リサーチ',
  p200: '物語',
  p300: '映像設計',
  p400: '台本・ナレーション',
  p500: '素材準備',
  p600: 'シーン画像',
  p700: '音声',
  p800: '動画',
  p900: '書き出し・確認',
  p550: '素材リクエスト作成',
  p560: '素材画像生成',
  p650: 'シーン画像リクエスト作成',
  p660: 'シーン画像生成',
};

const slotLabelJa: Record<string, string> = {
  p000: 'run 入口',
  p010: '現在位置の確認',
  p020: '次の人間レビュー',
  p030: 'ステージ表',
  p040: '成果物一覧',
  p050: '補足メモ',
  p110: 'リサーチ準備',
  p120: 'リサーチ本文作成',
  p130: 'リサーチ評価・改善',
  p210: '物語準備',
  p220: '物語本文作成',
  p230: '物語評価・改善',
  p310: '映像価値設計',
  p320: '映像設計の評価・改善',
  p330: '後工程への引き継ぎ',
  p410: '台本準備',
  p420: '台本・ナレーション原稿作成',
  p430: '台本評価・改善',
  p440: '人間修正・ナレーション同期',
  p450: '映像マニフェスト作成',
  p510: '素材準備の確認',
  p520: '再利用素材の棚卸し',
  p530: '素材計画作成',
  p540: '素材計画の評価・改善',
  p550: '素材リクエスト作成',
  p560: '素材画像生成',
  p570: '素材の一貫性確認',
  p610: 'シーン画像準備',
  p620: 'シーンプロンプト作成',
  p630: 'シーン構造の評価・改善',
  p640: '画像判断の評価・改善',
  p650: 'シーン画像リクエスト確定',
  p660: 'シーン画像生成',
  p670: '画像QA・修正',
  p680: '画像レビュー引き継ぎ',
  p710: 'ナレーション準備',
  p720: '音声テキスト同期',
  p730: '音声生成',
  p740: '音声尺合わせ',
  p750: '音声QA・レビュー',
  p810: '動画準備',
  p820: '動画プロンプト作成',
  p830: '動画リクエスト確定',
  p840: '動画生成',
  p850: '動画レビュー',
  p910: '結合入力作成',
  p920: '動画書き出し',
  p930: '最終QA',
};

function stageDisplayLabel(stage: RunStage): string {
  return stageLabelJa[stage.code] ?? stage.label;
}

function slotDisplayLabel(slot: RunSlot): string {
  return slotLabelJa[slot.code] ?? slot.purpose;
}

function currentStageCaption(stage: RunStage): string {
  if (stage.state === 'pending' && stage.code === 'p550') return `${stage.code} ${stageDisplayLabel(stage)} 未生成`;
  if (stage.state === 'pending' && stage.code === 'p650') return `${stage.code} ${stageDisplayLabel(stage)} 未生成`;
  return `${stage.code} ${stageDisplayLabel(stage)} ${stageStateLabel(stage.state)}`;
}

function currentStageTitle(stage: RunStage): string {
  if (stage.state === 'pending') return `次: ${stage.code} / ${stageDisplayLabel(stage)}`;
  return `${stage.code} / ${stageDisplayLabel(stage)}`;
}

function parentStageCode(code: string): string {
  return /^p\d{3}$/.test(code) ? `${code.slice(0, 2)}00` : code;
}

function RunProgressPanel({ progress }: { progress: RunProgress | null }) {
  if (!progress || !progress.stages.length) return null;
  const mainStages = progress.stages.filter((stage) => /^p[1-9]00$/.test(stage.code));
  const current = progress.currentStage;
  const stageDescriptions = mainStages.map((stage) => ({
    stage,
    slots: progress.slots.filter((slot) => parentStageCode(slot.code) === stage.code),
  }));
  return (
    <Box className="runProgressPanel">
      <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1} className="runProgressHeader">
        <Box minWidth={0}>
          <Typography variant="caption" color="text.secondary">レポ進捗</Typography>
          <Typography fontWeight={900} noWrap>
            {current ? currentStageTitle(current) : progress.runtimeStage || progress.status || '進捗待ち'}
          </Typography>
        </Box>
        <Chip size="small" color="primary" label={`${progress.doneCount}/${progress.totalCount}`} />
      </Stack>
      <LinearProgress variant="determinate" value={Math.max(0, Math.min(100, progress.percent))} />
      <Box className="runStageRail" aria-label="ToC進捗ステージ">
        {mainStages.map((stage) => (
          <Chip
            key={stage.code}
            size="small"
            label={`${stage.code} ${stageDisplayLabel(stage)} ${stageStateLabel(stage.state)}`}
            color={stage.code === current?.code ? 'primary' : stage.state === 'done' ? 'success' : 'default'}
            variant={stage.code === current?.code || stage.state === 'done' ? 'filled' : 'outlined'}
          />
        ))}
      </Box>
      <Typography variant="caption" color="text.secondary">
        {progress.runtimeStage ? `runtime.stage: ${progress.runtimeStage}` : 'state.txt / p000_index.md の進捗を表示しています'}
      </Typography>
      <Divider flexItem />
      <Box className="stageCatalog" aria-label="Pステージと小番号一覧">
        {stageDescriptions.map(({ stage, slots }) => (
          <Box key={stage.code} className="stageCatalogGroup">
            <Stack direction="row" spacing={0.75} alignItems="center" className="stageCatalogTitle">
              <Chip size="small" label={stage.code} color={stage.code === parentStageCode(current?.code || '') ? 'primary' : 'default'} />
              <Typography fontWeight={900}>{stageDisplayLabel(stage)}</Typography>
              <Typography variant="caption" color="text.secondary">{stageStateLabel(stage.state)}</Typography>
            </Stack>
            <Box className="slotList">
              {slots.map((slot) => (
                <Box key={slot.code} className="slotRow">
                  <Chip size="small" label={slot.code} variant="outlined" />
                  <Box minWidth={0}>
                    <Typography variant="body2" fontWeight={800}>{slotDisplayLabel(slot)}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {slot.requirement}
                      {slot.state ? ` / ${stageStateLabel(slot.state)}` : ''}
                      {slot.plannedArtifacts.length ? ` / ${slot.plannedArtifacts.join(', ')}` : ''}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function assetPromptFromDesign(ref: ReferenceOption): string {
  if (ref.path.startsWith('assets/characters/')) {
    return [
      '[素材設計]',
      'この画像は後続 cut の continuity anchor として使う character_reference。',
      '',
      '[生成方針]',
      '顔、髪型、衣装、年齢感、体格、シルエットが後続 scene で再利用できるように固定する。',
      '実写、シネマティック。文字なし、ロゴなし、ウォーターマークなし。',
      '',
      `[対象]`,
      `${ref.label} のキャラクター参照画像。`,
      '',
      '[禁止]',
      '別人化、衣装や年齢感の drift、文字、字幕、ロゴ。',
    ].join('\n');
  }
  if (ref.path.startsWith('assets/objects/')) {
    return [
      '[素材設計]',
      'この画像は後続 cut の continuity anchor として使う object_reference。',
      '',
      '[生成方針]',
      'silhouette、材質、装飾、縮尺感、工芸の痕跡を固定する。',
      '映像だけで物語上の役割が伝わるようにし、文字や銘板には頼らない。',
      '実写、シネマティック。文字なし、ロゴなし、ウォーターマークなし。',
      '',
      '[対象]',
      `${ref.label} のアイテム参照画像。`,
      '',
      '[禁止]',
      '文字、看板、銘板、説明的UI、字幕、ロゴ、単なる装飾への矮小化。',
    ].join('\n');
  }
  return [
    '[素材設計]',
    'この画像は後続 cut の continuity anchor として使う location_anchor。',
    '',
    '[生成方針]',
    'spatial identity、主要構造、光環境、場所固有の空気を固定する。',
    '独立した location anchor として、必要なら reference_inputs なしの bootstrap lane で成立させる。',
    '実写、シネマティック。文字なし、ロゴなし、ウォーターマークなし。人物を出さない。',
    '',
    '[対象]',
    `${ref.label} の場所参照画像。`,
    '',
    '[禁止]',
    '人物、群衆、字幕、ロゴ、看板、説明的な文字情報。',
  ].join('\n');
}

function existingAssetItems(refs: ReferenceOption[]): EditableItem[] {
  return refs
    .filter(
      (ref) =>
        ref.path.startsWith('assets/characters/') ||
        ref.path.startsWith('assets/objects/') ||
        ref.path.startsWith('assets/locations/') ||
        ref.path.startsWith('assets/location/'),
    )
    .map((ref) => {
      const assetType = ref.path.startsWith('assets/characters/')
        ? 'character'
        : ref.path.startsWith('assets/objects/')
          ? 'object'
          : 'location';
      return {
        id: ref.label,
        kind: 'asset',
        assetType,
        tool: null,
        output: ref.path,
        prompt: assetPromptFromDesign(ref),
        references: [],
        referenceCount: 0,
        executionLane: 'existing_asset',
        generationStatus: null,
        existingImage: ref.path,
        draftPrompt: assetPromptFromDesign(ref),
        selectedReferences: [],
        candidates: [],
        selectedCandidatePath: null,
        generating: false,
        promptGenerating: false,
        videoCandidates: [],
        videoGenerating: false,
        videoDraftPrompt: defaultVideoPrompt({
          id: ref.label,
          kind: 'asset',
          assetType,
          tool: null,
          output: ref.path,
          prompt: assetPromptFromDesign(ref),
          references: [],
          referenceCount: 0,
          executionLane: 'existing_asset',
          generationStatus: null,
          existingImage: ref.path,
        }),
        videoQuality: '1080p',
        videoAspectRatio: '16:9',
        videoDurationSec: 8,
        videoFirstReferencePath: ref.path,
        videoLastReferencePath: null,
        videoReferencePaths: [],
        videoTool: 'kling_3_0',
        sceneKey: null,
        sceneLabel: 'scene',
        narrationText: '',
        narrationTtsText: '',
        narrationOutput: null,
        narrationTool: 'elevenlabs',
        narrationDurationSec: null,
        narrationExists: false,
        narrationGenerating: false,
        renderVideoPath: null,
        renderVideoExists: false,
        renderVideoDurationSec: 8,
        renderNarrationPath: null,
        renderNarrationOffsetSec: 0,
      };
    });
}

function candidateSlots(item: EditableItem, count: number): Candidate[] {
  const slotCount = Math.max(count, item.candidates.length);
  return Array.from({ length: slotCount }, (_, index) => {
    const candidate = item.candidates[index];
    if (candidate) return candidate;
    return {
      index: index + 1,
      status: item.generating ? 'generating' : 'waiting',
      path: null,
    };
  });
}

function videoCandidateSlots(item: EditableItem, count: number): Candidate[] {
  const slotCount = Math.max(count, item.videoCandidates.length);
  return Array.from({ length: slotCount }, (_, index) => {
    const candidate = item.videoCandidates[index];
    if (candidate) return candidate;
    return {
      index: index + 1,
      status: item.videoGenerating ? 'generating' : 'waiting',
      path: null,
    };
  });
}

function labelFromPath(path: string): string {
  const filename = path.split('/').pop() || path;
  return filename.replace(/\.[^.]+$/, '');
}

function videoReferenceOptions(item: EditableItem, references: ReferenceOption[]): ReferenceOption[] {
  const byPath = new Map<string, ReferenceOption>();
  references.forEach((ref) => byPath.set(ref.path, ref));
  const addPath = (path: string | null | undefined, label?: string) => {
    if (!path || byPath.has(path)) return;
    byPath.set(path, { path, label: label || labelFromPath(path) });
  };
  addPath(item.existingImage, '現在の画像');
  item.candidates.forEach((candidate) => addPath(candidate.path, `候補 ${candidate.index}`));
  addPath(item.selectedCandidatePath, '採用候補');
  return Array.from(byPath.values());
}

type SceneVideoPanelProps = {
  item: EditableItem;
  runId: string;
  references: ReferenceOption[];
  videoGenerationBusy: boolean;
  videoCandidateCount: number;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
  onGenerateVideo: (item: EditableItem) => void;
};

function SceneVideoPanel({ item, runId, references, videoGenerationBusy, videoCandidateCount, onPatchItem, onGenerateVideo }: SceneVideoPanelProps) {
  const options = useMemo(() => videoReferenceOptions(item, references), [item, references]);
  const byPath = useMemo(() => new Map(options.map((option) => [option.path, option])), [options]);
  const firstReference = item.videoFirstReferencePath ? byPath.get(item.videoFirstReferencePath) ?? null : null;
  const lastReference = item.videoLastReferencePath ? byPath.get(item.videoLastReferencePath) ?? null : null;
  const videoReferences = item.videoReferencePaths.map((path) => byPath.get(path)).filter(Boolean) as ReferenceOption[];
  const videoSlots = useMemo(() => videoCandidateSlots(item, videoCandidateCount), [item, videoCandidateCount]);
  const narrationMinDuration = Math.max(1, Math.ceil(item.narrationDurationSec || 0));
  const previewPaths = Array.from(
    new Set(
      [
        item.videoFirstReferencePath,
        item.videoLastReferencePath,
        ...item.videoReferencePaths,
      ].filter(Boolean) as string[],
    ),
  );
  const handleGenerateVideo = useCallback(() => onGenerateVideo(item), [item, onGenerateVideo]);
  return (
    <Box className="sceneVideoPanel">
      <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}>
        <Box minWidth={0}>
          <Typography fontWeight={900}>動画プロンプト</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            first / last reference と画質をこのcutごとに固定
          </Typography>
        </Box>
        <Stack direction="row" spacing={0.75} alignItems="center">
          {item.narrationDurationSec ? <Chip size="small" label={`音声 ${item.narrationDurationSec.toFixed(1)}s`} /> : null}
          <Chip size="small" color="primary" label={`${item.videoQuality} / ${item.videoAspectRatio}`} />
        </Stack>
      </Stack>

      <TextField
        label="動画プロンプト"
        className="videoPromptEditor"
        multiline
        minRows={5}
        value={item.videoDraftPrompt}
        onChange={(event) => onPatchItem(item.id, { videoDraftPrompt: event.target.value })}
      />

      <Box className="videoSettingsGrid">
        <FormControl size="small">
          <InputLabel>画質</InputLabel>
          <Select
            label="画質"
            value={item.videoQuality}
            onChange={(event) => onPatchItem(item.id, { videoQuality: event.target.value })}
          >
            <MenuItem value="720p">720p</MenuItem>
            <MenuItem value="1080p">1080p</MenuItem>
            <MenuItem value="4K">4K</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small">
          <InputLabel>比率</InputLabel>
          <Select
            label="比率"
            value={item.videoAspectRatio}
            onChange={(event) => onPatchItem(item.id, { videoAspectRatio: event.target.value })}
          >
            <MenuItem value="16:9">16:9</MenuItem>
            <MenuItem value="9:16">9:16</MenuItem>
            <MenuItem value="1:1">1:1</MenuItem>
            <MenuItem value="4:3">4:3</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small">
          <InputLabel>tool</InputLabel>
          <Select
            label="tool"
            value={item.videoTool}
            onChange={(event) => onPatchItem(item.id, { videoTool: event.target.value })}
          >
            <MenuItem value="kling_3_0">Kling 3.0</MenuItem>
            <MenuItem value="kling_3_0_omni">Kling Omni</MenuItem>
            <MenuItem value="seedance">Seedance</MenuItem>
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="秒数"
          type="number"
          value={item.videoDurationSec}
          inputProps={{ min: narrationMinDuration, max: 60 }}
          onChange={(event) => {
            const next = Math.max(narrationMinDuration, Math.min(60, Number(event.target.value) || narrationMinDuration));
            onPatchItem(item.id, { videoDurationSec: next });
          }}
        />
      </Box>

      <Box className="videoFrameGrid">
        <Autocomplete
          options={options}
          value={firstReference}
          getOptionLabel={(option) => option.label}
          isOptionEqualToValue={(a, b) => a.path === b.path}
          onChange={(_, value) => onPatchItem(item.id, { videoFirstReferencePath: value?.path ?? null })}
          renderOption={(props, option) => (
            <Box component="li" {...props} className="refOption">
              <img src={fileUrl(runId, option.path)} alt="" loading="lazy" decoding="async" />
              <span>{option.label}</span>
            </Box>
          )}
          renderInput={(params) => <TextField {...params} label="first reference" size="small" />}
        />
        <Autocomplete
          options={options}
          value={lastReference}
          getOptionLabel={(option) => option.label}
          isOptionEqualToValue={(a, b) => a.path === b.path}
          onChange={(_, value) => onPatchItem(item.id, { videoLastReferencePath: value?.path ?? null })}
          renderOption={(props, option) => (
            <Box component="li" {...props} className="refOption">
              <img src={fileUrl(runId, option.path)} alt="" loading="lazy" decoding="async" />
              <span>{option.label}</span>
            </Box>
          )}
          renderInput={(params) => <TextField {...params} label="last reference" size="small" />}
        />
      </Box>

      <Autocomplete
        multiple
        options={options}
        value={videoReferences}
        getOptionLabel={(option) => option.label}
        isOptionEqualToValue={(a, b) => a.path === b.path}
        onChange={(_, value) => onPatchItem(item.id, { videoReferencePaths: value.map((option) => option.path) })}
        renderOption={(props, option) => (
          <Box component="li" {...props} className="refOption">
            <img src={fileUrl(runId, option.path)} alt="" loading="lazy" decoding="async" />
            <span>{option.label}</span>
          </Box>
        )}
        renderInput={(params) => <TextField {...params} label="補助reference" size="small" placeholder="必要な参照を追加" />}
      />

      <Box className="videoReferenceRail" aria-label="動画参照画像">
        {previewPaths.length ? (
          previewPaths.map((path) => (
            <Box key={path} className="referenceThumb videoReferenceThumb">
              <img src={fileUrl(runId, path)} alt={labelFromPath(path)} loading="lazy" decoding="async" />
              <Typography variant="caption" noWrap>{byPath.get(path)?.label ?? labelFromPath(path)}</Typography>
            </Box>
          ))
        ) : (
          <Typography variant="caption" color="text.secondary">動画reference未設定</Typography>
        )}
      </Box>

      <Box className="videoCandidateWall">
        <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
          <Box minWidth={0}>
            <Typography fontWeight={900}>動画生成スロット</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              このcutの候補動画を同時生成
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Chip size="small" label={`${videoCandidateCount}候補`} />
            <Button
              size="small"
              variant="outlined"
              startIcon={<MovieCreationIcon />}
              onClick={handleGenerateVideo}
              disabled={videoGenerationBusy || item.videoGenerating || !item.videoDraftPrompt.trim()}
            >
              このcutを動画生成
            </Button>
          </Stack>
        </Stack>
        {item.videoGenerating && <LinearProgress className="videoCandidateProgress" />}
        <Box
          className="videoCandidateGrid"
          style={{ gridTemplateColumns: `repeat(${Math.max(videoSlots.length, 1)}, minmax(180px, 1fr))` }}
        >
          {videoSlots.map((candidate) => (
            <Box
              key={`${item.id}-video-${candidate.index}`}
              className={`videoCandidateSlot${candidate.path ? ' has-video' : ''}${candidate.error ? ' is-error' : ''}`}
            >
              {candidate.path ? (
                <video src={videoFileUrl(runId, candidate.path)} controls muted playsInline preload="metadata" />
              ) : (
                <Typography variant="caption" color="text.secondary" className="videoSlotPlaceholder">
                  {videoCandidateDisplayMessage(candidate, item.videoGenerating)}
                </Typography>
              )}
              <Typography variant="caption" className="videoSlotLabel">
                候補 {candidate.index} / {item.videoQuality}
              </Typography>
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

type PromptCardProps = {
  item: EditableItem;
  runId: string;
  viewKind: ViewKind;
  references: ReferenceOption[];
  candidateCount: number;
  adoptedKeys: Set<string>;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
  onGenerateItem: (item: EditableItem) => void;
  onSetActiveItemId: (itemId: string) => void;
  onOpenImage: (image: EnlargedImage) => void;
};

const PromptCard = React.memo(function PromptCard({
  item,
  runId,
  viewKind,
  references,
  candidateCount,
  adoptedKeys,
  onPatchItem,
  onGenerateItem,
  onSetActiveItemId,
  onOpenImage,
}: PromptCardProps) {
  const slots = useMemo(() => candidateSlots(item, candidateCount), [candidateCount, item]);
  const cardClassName = useMemo(
    () => `promptCard ${viewKind === 'scene' ? 'is-scene' : ''} ${item.generating || item.promptGenerating ? 'is-generating' : ''}`,
    [item.generating, item.promptGenerating, viewKind],
  );
  const handleActivate = useCallback(() => onSetActiveItemId(item.id), [item.id, onSetActiveItemId]);
  const handlePromptChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => onPatchItem(item.id, { draftPrompt: event.target.value }),
    [item.id, onPatchItem],
  );
  const handleReferencesChange = useCallback(
    (_: React.SyntheticEvent, value: ReferenceOption[]) => onPatchItem(item.id, { selectedReferences: value }),
    [item.id, onPatchItem],
  );
  const handleGenerate = useCallback(() => onGenerateItem(item), [item, onGenerateItem]);
  const openExistingImage = useCallback((event?: React.MouseEvent | React.KeyboardEvent) => {
    if (!item.existingImage) return;
    event?.stopPropagation();
    onSetActiveItemId(item.id);
    onOpenImage({
      itemId: item.id,
      label: '現在',
      path: item.existingImage,
      src: fileUrl(runId, item.existingImage),
    });
  }, [item.existingImage, item.id, onOpenImage, onSetActiveItemId, runId]);
  const selectedReferenceThumbs = useMemo(
    () =>
      item.selectedReferences.map((ref) => {
        const removeReference = () =>
          onPatchItem(item.id, {
            selectedReferences: item.selectedReferences.filter((selected) => selected.path !== ref.path),
          });
        return (
          <Box key={ref.path} className="referenceThumb">
            <img src={fileUrl(runId, ref.path)} alt={ref.label} loading="lazy" decoding="async" />
            <Typography variant="caption" noWrap>{ref.label}</Typography>
            <IconButton size="small" aria-label={`${ref.label}を参照から外す`} onClick={removeReference}>
              ×
            </IconButton>
          </Box>
        );
      }),
    [item.id, item.selectedReferences, onPatchItem, runId],
  );

  return (
    <Card
      className={cardClassName}
      variant="outlined"
      onFocus={handleActivate}
      onMouseEnter={handleActivate}
    >
      <CardContent className="promptCardContent">
        <Box className="promptLayout">
          <Stack spacing={1.5} className="editorColumn">
          <Stack direction="row" justifyContent="space-between" gap={1}>
            <Box minWidth={0}>
              <Typography fontWeight={900} noWrap>
                {item.id}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {item.output || '出力先未設定'}
              </Typography>
            </Box>
            <Chip
              size="small"
              label={executionLaneLabel(item.executionLane)}
              color={item.executionLane === 'bootstrap_builtin' ? 'secondary' : 'default'}
            />
          </Stack>

          <TextField
            label="プロンプト"
            className="promptEditor"
            multiline
            minRows={7}
            value={item.draftPrompt}
            onChange={handlePromptChange}
          />

          <Autocomplete
            multiple
            options={references}
            value={item.selectedReferences}
            getOptionLabel={(option) => option.label}
            isOptionEqualToValue={(a, b) => a.path === b.path}
            onChange={handleReferencesChange}
            renderOption={(props, option) => (
              <Box component="li" {...props} className="refOption">
                <img src={fileUrl(runId, option.path)} alt="" loading="lazy" decoding="async" />
                <span>{option.label}</span>
              </Box>
            )}
            renderInput={(params) => <TextField {...params} label="参照画像" placeholder="何枚でも選択" />}
          />

          <Box className="referenceRail" aria-label="選択済み参照画像">
            {item.selectedReferences.length ? (
              selectedReferenceThumbs
            ) : (
              <Typography variant="caption" color="text.secondary">参照画像なし</Typography>
            )}
          </Box>

          <Button
            variant="contained"
            startIcon={<AutoAwesomeIcon />}
            disabled={item.generating || item.promptGenerating || !item.draftPrompt.trim()}
            onClick={handleGenerate}
          >
            {item.promptGenerating ? 'プロンプト作成中' : '画像生成'}
          </Button>
          </Stack>

          <Box className="comparisonWall">
            <Box className="comparisonHeader">
              <Typography fontWeight={900}>候補比較</Typography>
              <Chip size="small" label={item.promptGenerating ? 'プロンプト作成中' : item.generating ? '生成中' : item.candidates.length ? '確認待ち' : '未生成'} />
            </Box>
            <Box className="candidateGrid">
            {item.existingImage && (
              <GlassStatusRim
                variant="solid"
                density="compact"
                slot="candidate"
                status="idle"
                interactive
                className="candidate existing"
              >
                <Box
                  className="candidateMedia is-clickable"
                  role="button"
                  tabIndex={0}
                  aria-label={`${item.id}の現在の画像を拡大表示`}
                  onClick={openExistingImage}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      openExistingImage(event);
                    }
                  }}
                >
                  <img src={fileUrl(runId, item.existingImage)} alt="現在の画像" loading="lazy" decoding="async" />
                </Box>
                <Typography variant="caption" className="candidateLabel">現在</Typography>
              </GlassStatusRim>
            )}
            {slots.map((candidate) => {
              const isSelected = item.selectedCandidatePath === candidate.path;
              const isAdopted = Boolean(candidate.path && adoptedKeys.has(`${runId}:${candidate.path}`));
              const isPlaceholder = !candidate.path && !candidate.error;
              const selectCandidate = () => {
                if (candidate.path) {
                  onSetActiveItemId(item.id);
                  onPatchItem(item.id, { selectedCandidatePath: candidate.path });
                }
              };
              const openCandidate = (event?: React.MouseEvent | React.KeyboardEvent) => {
                if (!candidate.path) return;
                event?.stopPropagation();
                const label = `候補 ${candidate.index}`;
                selectCandidate();
                onOpenImage({
                  itemId: item.id,
                  label,
                  path: candidate.path,
                  src: fileUrl(runId, candidate.path),
                });
              };
              return (
                <GlassStatusRim
                  key={`${item.id}-${candidate.index}`}
                  variant="solid"
                  density="compact"
                  status={candidate.error ? 'error' : isAdopted ? 'success' : isSelected ? 'selected' : item.generating ? 'active' : 'idle'}
                  interactive={Boolean(candidate.path)}
                  selected={isSelected}
                  slot="candidate"
                  role={candidate.path ? 'button' : undefined}
                  aria-pressed={candidate.path ? isSelected : undefined}
                  aria-label={candidate.path ? `候補${candidate.index}を採用候補にする` : undefined}
                  className={`candidate ${isPlaceholder ? 'placeholderCandidate' : ''} ${isAdopted ? 'is-adopted' : ''}`}
                  onClick={selectCandidate}
                  onKeyDown={(event) => {
                    if ((event.key === 'Enter' || event.key === ' ') && candidate.path) {
                      event.preventDefault();
                      selectCandidate();
                    }
                  }}
                >
                  <Box
                    className={`candidateMedia ${candidate.path ? 'is-clickable' : ''}`}
                    role={candidate.path ? 'button' : undefined}
                    tabIndex={candidate.path ? 0 : undefined}
                    aria-label={candidate.path ? `候補${candidate.index}を拡大表示` : undefined}
                    onClick={candidate.path ? openCandidate : undefined}
                    onKeyDown={
                      candidate.path
                        ? (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              openCandidate(event);
                            }
                          }
                        : undefined
                    }
                  >
                    {candidate.path ? (
                      <img src={fileUrl(runId, candidate.path)} alt={`候補${candidate.index}`} loading="lazy" decoding="async" />
                    ) : (
                      <Typography className="candidateMessage">
                        {candidateDisplayMessage(candidate, item.generating)}
                      </Typography>
                    )}
                  </Box>
                  <Typography variant="caption" className="candidateLabel">
                    候補 {candidate.index}
                    {isAdopted ? ' / 採用済み' : isSelected ? ' / 採用候補' : ''}
                  </Typography>
                </GlassStatusRim>
              );
            })}
            </Box>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
});

type VideoCutCardProps = {
  item: EditableItem;
  runId: string;
  references: ReferenceOption[];
  videoGenerationBusy: boolean;
  videoCandidateCount: number;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
  onGenerateVideo: (item: EditableItem) => void;
};

const VideoCutCard = React.memo(function VideoCutCard({
  item,
  runId,
  references,
  videoGenerationBusy,
  videoCandidateCount,
  onPatchItem,
  onGenerateVideo,
}: VideoCutCardProps) {
  return (
    <Card className="videoCutCard" variant="outlined">
      <CardContent className="videoCutCardContent">
        <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} className="videoCutHeader">
          <Box minWidth={0}>
            <Typography fontWeight={900} noWrap>{item.id}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {item.output || '出力先未設定'}
            </Typography>
          </Box>
          <Chip size="small" color="primary" label={`${item.videoQuality} / ${item.videoAspectRatio}`} />
        </Stack>
        <SceneVideoPanel
          item={item}
          runId={runId}
          references={references}
          videoGenerationBusy={videoGenerationBusy}
          videoCandidateCount={videoCandidateCount}
          onPatchItem={onPatchItem}
          onGenerateVideo={onGenerateVideo}
        />
      </CardContent>
    </Card>
  );
});

type NarrationCutCardProps = {
  item: EditableItem;
  runId: string;
  narrationBusy: boolean;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
  onGenerateNarration: (item: EditableItem) => void;
};

const NarrationCutCard = React.memo(function NarrationCutCard({
  item,
  runId,
  narrationBusy,
  onPatchItem,
  onGenerateNarration,
}: NarrationCutCardProps) {
  const handleAudioPlay = useCallback((event: React.SyntheticEvent<HTMLAudioElement>) => {
    document.querySelectorAll('audio').forEach((audio) => {
      if (audio !== event.currentTarget) audio.pause();
    });
  }, []);
  const handleGenerate = useCallback(() => onGenerateNarration(item), [item, onGenerateNarration]);
  return (
    <Card className="narrationCutCard" variant="outlined">
      <CardContent className="narrationCutCardContent">
        <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} className="videoCutHeader">
          <Box minWidth={0}>
            <Typography fontWeight={900} noWrap>{item.id}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {item.narrationOutput || '音声出力先未設定'}
            </Typography>
          </Box>
          <Chip
            size="small"
            color={item.narrationExists ? 'success' : 'default'}
            label={item.narrationDurationSec ? `${item.narrationDurationSec.toFixed(1)}s` : item.narrationExists ? '生成済み' : '未生成'}
          />
        </Stack>

        <Box className="narrationPanel">
          <TextField
            label="ナレーション文面"
            multiline
            minRows={5}
            value={item.narrationText}
            onChange={(event) => onPatchItem(item.id, { narrationText: event.target.value })}
          />
          <TextField
            label="TTS文面"
            multiline
            minRows={3}
            value={item.narrationTtsText}
            onChange={(event) => onPatchItem(item.id, { narrationTtsText: event.target.value })}
          />
          <Box className="narrationSettingsGrid">
            <FormControl size="small">
              <InputLabel>tool</InputLabel>
              <Select
                label="tool"
                value={item.narrationTool}
                onChange={(event) => onPatchItem(item.id, { narrationTool: event.target.value })}
              >
                <MenuItem value="elevenlabs">ElevenLabs</MenuItem>
                <MenuItem value="silent">Silent</MenuItem>
                <MenuItem value="macos_say">macOS say</MenuItem>
              </Select>
            </FormControl>
            <TextField
              size="small"
              label="出力"
              value={item.narrationOutput || ''}
              onChange={(event) => onPatchItem(item.id, { narrationOutput: event.target.value || null })}
            />
          </Box>
          <Box className="audioReviewBox">
            {item.narrationExists && item.narrationOutput ? (
              <audio src={audioFileUrl(runId, item.narrationOutput)} controls preload="metadata" onPlay={handleAudioPlay} />
            ) : (
              <Typography variant="caption" color="text.secondary">音声ファイル未生成</Typography>
            )}
            <Button
              variant="contained"
              startIcon={<RecordVoiceOverIcon />}
              onClick={handleGenerate}
              disabled={narrationBusy || item.narrationGenerating || (item.narrationTool !== 'silent' && !item.narrationText.trim() && !item.narrationTtsText.trim())}
            >
              このcutの音声生成
            </Button>
          </Box>
          {item.narrationGenerating && <LinearProgress className="videoCandidateProgress" />}
        </Box>
      </CardContent>
    </Card>
  );
});

type RenderCutCardProps = {
  item: EditableItem;
  runId: string;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
};

const RenderCutCard = React.memo(function RenderCutCard({ item, runId, onPatchItem }: RenderCutCardProps) {
  const handleAudioPlay = useCallback((event: React.SyntheticEvent<HTMLAudioElement>) => {
    document.querySelectorAll('audio').forEach((audio) => {
      if (audio !== event.currentTarget) audio.pause();
    });
  }, []);
  const narrationDuration = item.narrationDurationSec || 0;
  const minVideoDuration = Math.max(1, Math.ceil(narrationDuration + item.renderNarrationOffsetSec));
  const isShort = item.renderVideoDurationSec < minVideoDuration;
  return (
    <Card className="renderCutCard" variant="outlined">
      <CardContent className="renderCutCardContent">
        <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} className="videoCutHeader">
          <Box minWidth={0}>
            <Typography fontWeight={900} noWrap>{item.id}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {item.renderVideoPath || '動画未選択'}
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.75}>
            <Chip size="small" color={item.renderVideoExists ? 'success' : 'default'} label={item.renderVideoExists ? '動画あり' : '動画なし'} />
            <Chip size="small" color={item.narrationExists ? 'success' : 'default'} label={item.narrationDurationSec ? `音声 ${item.narrationDurationSec.toFixed(1)}s` : '音声なし'} />
          </Stack>
        </Stack>
        <Box className="renderPanel">
          <Box className="renderMediaGrid">
            <Box className="renderMediaSlot">
              {item.renderVideoExists && item.renderVideoPath ? (
                <video src={videoFileUrl(runId, item.renderVideoPath)} controls muted playsInline preload="metadata" />
              ) : (
                <Typography variant="caption" color="text.secondary">動画なし</Typography>
              )}
            </Box>
            <Box className="renderAudioSlot">
              {item.narrationExists && item.renderNarrationPath ? (
                <audio src={audioFileUrl(runId, item.renderNarrationPath)} controls preload="metadata" onPlay={handleAudioPlay} />
              ) : (
                <Typography variant="caption" color="text.secondary">音声なし</Typography>
              )}
            </Box>
          </Box>
          <Box className="renderSettingsGrid">
            <TextField
              size="small"
              label="動画秒数"
              type="number"
              value={item.renderVideoDurationSec}
              inputProps={{ min: minVideoDuration, max: 600 }}
              onChange={(event) => {
                const next = Math.max(minVideoDuration, Math.min(600, Number(event.target.value) || minVideoDuration));
                onPatchItem(item.id, { renderVideoDurationSec: next, videoDurationSec: next });
              }}
            />
            <TextField
              size="small"
              label="話し出し秒"
              type="number"
              value={item.renderNarrationOffsetSec}
              inputProps={{ min: 0, max: 120, step: 0.1 }}
              onChange={(event) => {
                const next = Math.max(0, Math.min(120, Number(event.target.value) || 0));
                const nextMin = Math.max(1, Math.ceil(narrationDuration + next));
                onPatchItem(item.id, {
                  renderNarrationOffsetSec: next,
                  renderVideoDurationSec: Math.max(item.renderVideoDurationSec, nextMin),
                  videoDurationSec: Math.max(item.videoDurationSec, nextMin),
                });
              }}
            />
            <TextField
              size="small"
              label="動画path"
              value={item.renderVideoPath || ''}
              onChange={(event) => onPatchItem(item.id, { renderVideoPath: event.target.value || null })}
            />
            <TextField
              size="small"
              label="音声path"
              value={item.renderNarrationPath || ''}
              onChange={(event) => onPatchItem(item.id, { renderNarrationPath: event.target.value || null })}
            />
          </Box>
          {isShort && <Chip size="small" color="warning" label={`最低 ${minVideoDuration}s`} />}
        </Box>
      </CardContent>
    </Card>
  );
});

function App() {
  const [runs, setRuns] = useState<RunFolder[]>([]);
  const [runId, setRunId] = useState('');
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('image');
  const [viewKind, setViewKind] = useState<ViewKind>('asset');
  const [assetFilter, setAssetFilter] = useState<AssetFilter>('asset');
  const [candidateCount, setCandidateCount] = useState(2);
  const [candidateCountDraft, setCandidateCountDraft] = useState(2);
  const [videoCandidateCount, setVideoCandidateCount] = useState(3);
  const [videoCandidateCountDraft, setVideoCandidateCountDraft] = useState(3);
  const [activeVideoSceneKey, setActiveVideoSceneKey] = useState('');
  const [items, setItems] = useState<EditableItem[]>([]);
  const [references, setReferences] = useState<ReferenceOption[]>([]);
  const [runProgress, setRunProgress] = useState<RunProgress | null>(null);
  const [busy, setBusy] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string }>>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [approvalCount, setApprovalCount] = useState(0);
  const [approvals, setApprovals] = useState<unknown[]>([]);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [isNarrowViewport, setIsNarrowViewport] = useState(false);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [bulkGenerating, setBulkGenerating] = useState(false);
  const [bulkTotal, setBulkTotal] = useState(0);
  const [bulkCompletedCount, setBulkCompletedCount] = useState(0);
  const [bulkFailedCount, setBulkFailedCount] = useState(0);
  const [videoBulkTotal, setVideoBulkTotal] = useState(0);
  const [videoBulkCompletedCount, setVideoBulkCompletedCount] = useState(0);
  const [videoBulkFailedCount, setVideoBulkFailedCount] = useState(0);
  const [narrationBusy, setNarrationBusy] = useState(false);
  const [narrationStatus, setNarrationStatus] = useState<string | null>(null);
  const [narrationBulkTotal, setNarrationBulkTotal] = useState(0);
  const [narrationBulkCompletedCount, setNarrationBulkCompletedCount] = useState(0);
  const [narrationBulkFailedCount, setNarrationBulkFailedCount] = useState(0);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderStatus, setRenderStatus] = useState<string | null>(null);
  const [insertBusy, setInsertBusy] = useState(false);
  const [insertStatus, setInsertStatus] = useState<InsertStatus>('idle');
  const [lastInsertedCount, setLastInsertedCount] = useState(0);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [insertedKeys, setInsertedKeys] = useState<Set<string>>(() => new Set());
  const [createRunOpen, setCreateRunOpen] = useState(false);
  const [createRunTitle, setCreateRunTitle] = useState('');
  const [createRunSource, setCreateRunSource] = useState('');
  const [createRunBusy, setCreateRunBusy] = useState(false);
  const [createRunStatus, setCreateRunStatus] = useState<string | null>(null);
  const [createRunError, setCreateRunError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTarget, setSettingsTarget] = useState<SettingsTarget>('character');
  const [settingContent, setSettingContent] = useState('');
  const [settingPath, setSettingPath] = useState('');
  const [settingDraft, setSettingDraft] = useState('');
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [confirmRegenerateOpen, setConfirmRegenerateOpen] = useState(false);
  const [confirmImageGenerateOpen, setConfirmImageGenerateOpen] = useState(false);
  const [confirmVideoPromptOpen, setConfirmVideoPromptOpen] = useState(false);
  const [pendingWorkspaceMode, setPendingWorkspaceMode] = useState<WorkspaceMode | null>(null);
  const [enlargedImage, setEnlargedImage] = useState<EnlargedImage | null>(null);
  const [regenerateBusy, setRegenerateBusy] = useState(false);
  const [regenerateStatus, setRegenerateStatus] = useState<string | null>(null);
  const [regeneratedItems, setRegeneratedItems] = useState<EditableItem[]>([]);
  const [reviewSaveBusy, setReviewSaveBusy] = useState(false);
  const [reviewSaveStatus, setReviewSaveStatus] = useState<string | null>(null);
  const [videoPromptBusy, setVideoPromptBusy] = useState(false);
  const [videoPromptStatus, setVideoPromptStatus] = useState<string | null>(null);
  const [addCutOpen, setAddCutOpen] = useState(false);
  const [addCutAnchorId, setAddCutAnchorId] = useState('');
  const [addCutPosition, setAddCutPosition] = useState<'before' | 'after' | 'end'>('after');
  const [addCutName, setAddCutName] = useState('');
  const [addCutBusy, setAddCutBusy] = useState(false);
  const [addCutError, setAddCutError] = useState<string | null>(null);
  const [addAssetOpen, setAddAssetOpen] = useState(false);
  const [addAssetType, setAddAssetType] = useState<AssetCreateType>('character');
  const [addAssetTitle, setAddAssetTitle] = useState('');
  const [addAssetBusy, setAddAssetBusy] = useState(false);
  const [addAssetError, setAddAssetError] = useState<string | null>(null);
  const mobileChatButtonRef = useRef<HTMLButtonElement | null>(null);
  const chatInputRef = useRef<HTMLInputElement | null>(null);
  const selectedRun = useMemo(() => runs.find((run) => run.id === runId), [runId, runs]);
  const requestKind = workspaceMode === 'image' ? viewKind : 'scene';
  const visibleItems = useMemo(() => {
    if (workspaceMode !== 'image') return items.filter(isSceneCutItem);
    if (viewKind === 'scene') return items.filter(isSceneCutItem);
    const existingItemsByOutput = new Map(items.map((item) => [item.output, item]));
    const fallbackItems = existingAssetItems(references).filter((item) => !existingItemsByOutput.has(item.output));
    return sortAssetItems([...items, ...fallbackItems].filter((item) => itemMatchesAssetFilter(item, assetFilter)));
  }, [assetFilter, items, references, viewKind, workspaceMode]);
  const videoSceneGroups = useMemo(() => {
    const groups = new Map<string, { key: string; label: string; items: EditableItem[] }>();
    for (const item of visibleItems) {
      const key = item.sceneKey || 'scene';
      const existing = groups.get(key);
      if (existing) {
        existing.items.push(item);
      } else {
        groups.set(key, { key, label: item.sceneLabel || sceneLabelFromKey(key), items: [item] });
      }
    }
    return Array.from(groups.values());
  }, [visibleItems]);
  const activeVideoScene = useMemo(
    () => videoSceneGroups.find((group) => group.key === activeVideoSceneKey) ?? videoSceneGroups[0] ?? null,
    [activeVideoSceneKey, videoSceneGroups],
  );
  const videoDisplayItems = workspaceMode === 'video' ? activeVideoScene?.items ?? [] : visibleItems;
  const displayedItemCount = workspaceMode === 'video' ? videoDisplayItems.length : visibleItems.length;
  const imageGenerationActive = bulkGenerating || regenerateBusy || addAssetBusy || items.some((item) => item.generating || item.promptGenerating);
  const narrationGenerationActive = narrationBusy || items.some((item) => item.narrationGenerating);
  const videoGenerationActive = videoPromptBusy || items.some((item) => item.videoGenerating);
  const generationInFlight = imageGenerationActive || narrationGenerationActive || videoGenerationActive || renderBusy;
  const backgroundGenerationLabel = useMemo(() => {
    if (workspaceMode !== 'image' && imageGenerationActive) return '画像生成が別画面で進行中';
    if (workspaceMode !== 'narration' && narrationGenerationActive) return '音声生成が別画面で進行中';
    if (workspaceMode !== 'video' && videoGenerationActive) return '動画生成が別画面で進行中';
    if (workspaceMode !== 'render' && renderBusy) return '最終処理が別画面で進行中';
    return null;
  }, [imageGenerationActive, narrationGenerationActive, renderBusy, videoGenerationActive, workspaceMode]);
  const breadcrumb = useMemo(
    () => workspaceMode !== 'image'
      ? workspaceModeLabel(workspaceMode)
      : [viewLabel(viewKind), viewKind === 'asset' ? assetFilterLabel(assetFilter) : null].filter(Boolean).join(' / '),
    [assetFilter, viewKind, workspaceMode],
  );
  const currentSettingsTarget = useMemo<SettingsTarget | null>(() => {
    if (workspaceMode !== 'image' || viewKind === 'scene') return 'scene';
    if (assetFilter === 'chara') return 'character';
    if (assetFilter === 'obj') return 'item';
    if (assetFilter === 'location') return 'location';
    return null;
  }, [assetFilter, viewKind, workspaceMode]);
  const activeItem = useMemo(
    () => visibleItems.find((item) => item.id === activeItemId) ?? visibleItems[0] ?? null,
    [activeItemId, visibleItems],
  );
  const displayedCandidateCount = useMemo(() => Math.round(candidateCountDraft), [candidateCountDraft]);
  const displayedVideoCandidateCount = useMemo(() => Math.round(videoCandidateCountDraft), [videoCandidateCountDraft]);
  const addAssetDesignPrompt = useMemo(() => assetCreateDesignPrompt(addAssetType, addAssetTitle), [addAssetTitle, addAssetType]);

  const ensureItemsInState = useCallback((targetItems: EditableItem[]) => {
    if (!targetItems.length) return;
    setItems((prev) => {
      const existingIds = new Set(prev.map((item) => item.id));
      const additions = targetItems.filter((item) => !existingIds.has(item.id));
      return additions.length ? [...prev, ...additions] : prev;
    });
  }, []);

  const loadRuns = useCallback(async (preferredRunId?: string) => {
    const data = await jsonFetch<{ runs: RunFolder[] }>('/api/image-gen/runs');
    setRuns(data.runs);
    setRunId((current) => preferredRunId || current || data.runs[0]?.id || '');
    return data.runs;
  }, []);

  const loadRunRequests = useCallback(async (targetRunId: string, targetKind: ViewKind) => {
    setBusy(true);
    try {
      const data = await jsonFetch<{ items: ImageRequestItem[]; references: ReferenceOption[]; progress: RunProgress }>(
        `/api/image-gen/requests?run_id=${encodeURIComponent(targetRunId)}&kind=${targetKind}`,
      );
      let narrationById: Map<string, NarrationManifestItem> | undefined;
      let progress = data.progress;
      if (targetKind === 'scene') {
        try {
          const narrationData = await jsonFetch<{ items: NarrationManifestItem[]; progress: RunProgress }>(
            `/api/image-gen/narration-items?run_id=${encodeURIComponent(targetRunId)}`,
          );
          narrationById = new Map(narrationData.items.map((item) => [item.itemId, item]));
          progress = narrationData.progress || progress;
        } catch (error) {
          console.error(error);
        }
      }
      const loadedItems = toEditableItems(data.items, data.references, narrationById);
      setReferences(data.references);
      setItems((prev) => mergeLoadedItemsWithInflight(prev, loadedItems));
      setRunProgress(progress);
    } catch (error) {
      console.error(error);
      setItems([]);
      setReferences([]);
      setRunProgress(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    loadRuns()
      .catch((error) => console.error(error));
  }, [loadRuns]);

  useEffect(() => {
    if (!runId) return;
    void loadRunRequests(runId, requestKind);
  }, [loadRunRequests, requestKind, runId]);

  useEffect(() => {
    if (!runId || !generationInFlight) return;
    let cancelled = false;
    const pollProgress = async () => {
      try {
        const data = await jsonFetch<ProgressResponse>(`/api/image-gen/progress?run_id=${encodeURIComponent(runId)}`);
        if (!cancelled) setRunProgress(data.progress);
      } catch (error) {
        console.error(error);
      }
    };
    void pollProgress();
    const timer = window.setInterval(() => {
      void pollProgress();
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [generationInFlight, runId]);

  useEffect(() => {
    if (workspaceMode !== 'video') return;
    setActiveVideoSceneKey((current) => {
      if (current && videoSceneGroups.some((group) => group.key === current)) return current;
      return videoSceneGroups[0]?.key || '';
    });
  }, [videoSceneGroups, workspaceMode]);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1100px)');
    const update = () => setIsNarrowViewport(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!isNarrowViewport || !chatOpen) return;
    window.setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [chatOpen, isNarrowViewport]);

  useEffect(() => {
    if (!settingsOpen) return;
    setSettingsBusy(true);
    setSettingsError(null);
    jsonFetch<PromptSettingResponse>(`/api/image-gen/prompt-settings?target=${settingsTarget}`)
      .then((data) => {
        setSettingContent(data.content);
        setSettingPath(data.path);
        setSettingDraft('');
      })
      .catch((error) => {
        console.error(error);
        setSettingsError('設定の読み込みに失敗');
        setSettingContent('');
        setSettingPath('');
      })
      .finally(() => setSettingsBusy(false));
  }, [settingsOpen, settingsTarget]);

  const selectedForInsert = useMemo(
    () => items.filter((item) => item.selectedCandidatePath && item.output),
    [items],
  );
  const adoptedKeys = insertedKeys;

  const patchItem = useCallback((itemId: string, patch: Partial<EditableItem>) => {
    setItems((prev) => prev.map((item) => (item.id === itemId ? { ...item, ...patch } : item)));
  }, []);

  const closeChat = useCallback(() => {
    setChatOpen(false);
    if (isNarrowViewport) {
      window.setTimeout(() => mobileChatButtonRef.current?.focus(), 0);
    }
  }, [isNarrowViewport]);

  const setActiveItemIdStable = useCallback((itemId: string) => setActiveItemId(itemId), []);
  const openEnlargedImage = useCallback((image: EnlargedImage) => setEnlargedImage(image), []);
  const closeEnlargedImage = useCallback(() => setEnlargedImage(null), []);

  const fetchCandidates = useCallback(
    (itemId: string) =>
      jsonFetch<CandidatesResponse>(
        `/api/image-gen/candidates?run_id=${encodeURIComponent(runId)}&item_id=${encodeURIComponent(itemId)}`,
      ),
    [runId],
  );

  const waitForRecoveredCandidates = useCallback(
    async (itemId: string, expectedCount: number, sinceMs: number, shouldStop?: () => boolean): Promise<CandidatesResponse> => {
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await sleep(2000);
        if (shouldStop?.()) throw new Error('candidate recovery cancelled');
        const data = await fetchCandidates(itemId);
        if (shouldStop?.()) throw new Error('candidate recovery cancelled');
        const completed = data.candidates.filter((candidate) => candidate.path && (candidate.mtimeMs ?? 0) >= sinceMs);
        if (completed.length >= expectedCount) {
          return { ...data, candidates: completed };
        }
      }
      throw new Error('candidate recovery timed out');
    },
    [fetchCandidates],
  );

  const generateWithRecovery = useCallback(
    async (item: EditableItem): Promise<CandidatesResponse> => {
      const startedAtMs = Date.now() - 1000;
      const controller = new AbortController();
      const generation = jsonFetch<CandidatesResponse>('/api/image-gen/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          run_id: runId,
          kind: viewKind,
          item_id: item.id,
          prompt: item.draftPrompt,
          references: item.selectedReferences.map((ref) => ref.path),
          candidate_count: candidateCount,
        }),
      });
      let generationSettled = false;
      const trackedGeneration = generation.finally(() => {
        generationSettled = true;
      });
      const recovery = waitForRecoveredCandidates(item.id, candidateCount, startedAtMs, () => generationSettled).then((data) => {
        controller.abort();
        return data;
      });
      return Promise.race([trackedGeneration, recovery]);
    },
    [candidateCount, runId, viewKind, waitForRecoveredCandidates],
  );

  const generateItem = useCallback(async (item: EditableItem) => {
    if (!runId) return;
    ensureItemsInState([item]);
    setActiveItemId(item.id);
    setInsertStatus('idle');
    patchItem(item.id, { generating: true, candidates: [] });
    try {
      const data = await generateWithRecovery(item);
      patchItem(item.id, {
        candidates: data.candidates,
        selectedCandidatePath: data.candidates.find((candidate) => candidate.path)?.path ?? null,
      });
    } catch (error) {
      console.error(error);
      patchItem(item.id, { candidates: [{ index: 1, status: 'failed', path: null, error: candidateErrorMessage(error) }] });
    } finally {
      patchItem(item.id, { generating: false });
    }
  }, [ensureItemsInState, generateWithRecovery, patchItem, runId]);

  const generateItems = useCallback(async (targetItems: EditableItem[]) => {
    if (!runId) return;
    ensureItemsInState(targetItems);
    const targetIds = new Set(targetItems.map((item) => item.id));
    const concurrency = Math.min(Math.max(candidateCount, 1), 4, Math.max(targetItems.length, 1));
    setBulkGenerating(true);
    setBulkTotal(targetIds.size);
    setBulkCompletedCount(0);
    setBulkFailedCount(0);
    setInsertStatus('idle');
    setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, generating: true, candidates: [] } : item)));
    let completed = 0;
    let failed = 0;
    let cursor = 0;

    const runNext = async (): Promise<void> => {
      const item = targetItems[cursor];
      cursor += 1;
      if (!item) return;
      try {
        const data = await generateWithRecovery(item);
        const hasCandidate = data.candidates.some((candidate) => candidate.path);
        if (hasCandidate) completed += 1;
        else failed += 1;
        setItems((prev) =>
          prev.map((prevItem) =>
            prevItem.id === item.id
              ? {
                  ...prevItem,
                  generating: false,
                  candidates: data.candidates,
                  selectedCandidatePath: data.candidates.find((candidate) => candidate.path)?.path ?? null,
                }
              : prevItem,
          ),
        );
      } catch (error) {
        failed += 1;
        setItems((prev) =>
          prev.map((prevItem) =>
            prevItem.id === item.id
              ? {
                  ...prevItem,
                  generating: false,
                  candidates: [{ index: 1, status: 'failed', path: null, error: candidateErrorMessage(error) }],
                }
              : prevItem,
          ),
        );
      } finally {
        setBulkCompletedCount(completed);
        setBulkFailedCount(failed);
        await runNext();
      }
    };

    try {
      await Promise.all(Array.from({ length: concurrency }, () => runNext()));
    } finally {
      setBulkGenerating(false);
    }
  }, [candidateCount, ensureItemsInState, generateWithRecovery, runId]);

  const generateBulk = async () => {
    await generateItems([...visibleItems]);
  };

  const downloadZip = async () => {
    if (!runId) return;
    setDownloadError(null);
    const paths = visibleItems.flatMap((item) => item.candidates.map((candidate) => candidate.path).filter(Boolean)) as string[];
    try {
      const response = await fetch('/api/image-gen/download-zip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, paths }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || response.statusText);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'image-gen-candidates.zip';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
      setDownloadError('DL失敗');
    }
  };

  const insertBulk = async () => {
    setInsertBusy(true);
    setInsertStatus('running');
    setLastInsertedCount(0);
    try {
      await jsonFetch('/api/image-gen/insert-bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: selectedForInsert.map((item) => ({
            run_id: runId,
            candidate_path: item.selectedCandidatePath,
            output: item.output,
          })),
        }),
      });
      setLastInsertedCount(selectedForInsert.length);
      setInsertedKeys((prev) => {
        const next = new Set(prev);
        selectedForInsert.forEach((item) => {
          if (item.selectedCandidatePath) next.add(`${runId}:${item.selectedCandidatePath}`);
        });
        return next;
      });
      setInsertStatus('success');
    } catch (error) {
      console.error(error);
      setInsertStatus('error');
    } finally {
      setInsertBusy(false);
    }
  };

  const savePermanentSetting = async () => {
    if (!settingDraft.trim()) return;
    setSettingsBusy(true);
    setSettingsError(null);
    try {
      const data = await jsonFetch<PromptSettingResponse>('/api/image-gen/prompt-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: settingsTarget, content: settingDraft.trim() }),
      });
      setSettingContent(data.content);
      setSettingPath(data.path);
      setSettingDraft('');
      setRegenerateStatus('恒常設定を更新しました');
    } catch (error) {
      console.error(error);
      setSettingsError('恒常設定の更新に失敗');
    } finally {
      setSettingsBusy(false);
    }
  };

  const openRegenerateConfirm = () => {
    if (!runId || !settingDraft.trim()) return;
    setSettingsError(null);
    setConfirmRegenerateOpen(true);
  };

  const regeneratePrompts = async () => {
    if (!runId || !settingDraft.trim()) return;
    const currentTargetVisible = currentSettingsTarget === settingsTarget;
    const targetItems = currentTargetVisible
      ? visibleItems.filter((item) => item.executionLane !== 'existing_asset')
      : [];
    const targetIds = new Set(targetItems.map((item) => item.id));
    const nextView = targetToMainView(settingsTarget);
    setConfirmRegenerateOpen(false);
    setSettingsOpen(false);
    setViewKind(nextView.viewKind);
    setAssetFilter(nextView.assetFilter);
    setActiveItemId(targetItems[0]?.id ?? null);
    setRegenerateBusy(true);
    setRegenerateStatus(`${settingsTargetLabel(settingsTarget)}のプロンプトを生成中`);
    setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, generating: true } : item)));
    try {
      const data = await jsonFetch<RegeneratePromptsResponse>('/api/image-gen/regenerate-prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          target: settingsTarget,
          instruction: settingDraft.trim(),
          item_ids: currentTargetVisible ? targetItems.map((item) => item.id) : [],
        }),
      });
      const byId = new Map(data.prompts.map((item) => [item.itemId, item.prompt]));
      const requestKind = nextView.viewKind;
      const requestData = await jsonFetch<{ items: ImageRequestItem[]; references: ReferenceOption[] }>(
        `/api/image-gen/requests?run_id=${encodeURIComponent(runId)}&kind=${requestKind}`,
      );
      setReferences(requestData.references);
      const loadedItems = toEditableItems(requestData.items, requestData.references);
      const nextGenerated = loadedItems
        .filter((item) => byId.has(item.id))
        .map((item) => {
          const prompt = byId.get(item.id) ?? item.draftPrompt;
          return { ...item, prompt, draftPrompt: prompt, candidates: [], selectedCandidatePath: null, generating: false };
        });
      const generatedById = new Map(nextGenerated.map((item) => [item.id, item]));
      setItems(loadedItems.map((item) => generatedById.get(item.id) ?? item));
      setRegeneratedItems(nextGenerated);
      setRegenerateStatus(`${data.updated.length}件のプロンプトを更新しました`);
      setSettingDraft('');
      setConfirmImageGenerateOpen(nextGenerated.length > 0);
    } catch (error) {
      console.error(error);
      setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, generating: false } : item)));
      setRegenerateStatus('プロンプト再生成に失敗');
    } finally {
      setRegenerateBusy(false);
    }
  };

  const generateRegeneratedImages = async () => {
    const targetItems = [...regeneratedItems];
    setConfirmImageGenerateOpen(false);
    setRegeneratedItems([]);
    await generateItems(targetItems);
  };

  const buildReviewItems = useCallback((targetItems: EditableItem[]) => targetItems.map((item) => ({
    item_id: item.id,
    kind: item.kind,
    output: item.output,
    prompt: item.draftPrompt,
    references: item.selectedReferences.map((ref) => ref.path),
    selected_candidate_path: item.selectedCandidatePath,
    existing_image: item.existingImage,
    video_prompt: item.videoDraftPrompt,
    video_quality: item.videoQuality,
    video_aspect_ratio: item.videoAspectRatio,
    video_duration_seconds: item.videoDurationSec,
    video_first_reference: item.videoFirstReferencePath || item.selectedCandidatePath || item.existingImage || item.output,
    video_last_reference: item.videoLastReferencePath,
    video_references: item.videoReferencePaths,
    video_tool: item.videoTool,
    narration_text: item.narrationText,
    narration_tts_text: item.narrationTtsText,
    narration_output: item.narrationOutput,
    narration_tool: item.narrationTool,
    render_video_path: item.renderVideoPath,
    render_narration_path: item.renderNarrationPath,
    render_video_duration_seconds: item.renderVideoDurationSec,
    render_narration_offset_seconds: item.renderNarrationOffsetSec,
  })), []);

  const saveCurrentReview = useCallback(async () => {
    if (!runId) return;
    const reviewKind = workspaceMode === 'image' ? viewKind : workspaceMode;
    setReviewSaveBusy(true);
    setReviewSaveStatus('保存中');
    try {
      const data = await jsonFetch<FrontendReviewResponse>('/api/image-gen/reviews/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          kind: reviewKind,
          note: 'frontend temporary save',
          items: buildReviewItems(visibleItems),
        }),
      });
      if (data.progress) setRunProgress(data.progress);
      setReviewSaveStatus(data.path ? `一時保存 ${data.path}` : '一時保存しました');
    } catch (error) {
      console.error(error);
      setReviewSaveStatus('一時保存失敗');
    } finally {
      setReviewSaveBusy(false);
    }
  }, [buildReviewItems, runId, viewKind, visibleItems, workspaceMode]);

  const applyWorkspaceMode = useCallback((nextMode: WorkspaceMode) => {
    setWorkspaceMode(nextMode);
    if (nextMode !== 'image') {
      setViewKind('scene');
      setAssetFilter('asset');
    }
  }, []);

  const switchWorkspaceMode = useCallback((nextMode: WorkspaceMode) => {
    if (nextMode === workspaceMode) return;
    if (generationInFlight) {
      setPendingWorkspaceMode(nextMode);
      return;
    }
    applyWorkspaceMode(nextMode);
  }, [applyWorkspaceMode, generationInFlight, workspaceMode]);

  const confirmWorkspaceSwitch = useCallback(() => {
    if (!pendingWorkspaceMode) return;
    applyWorkspaceMode(pendingWorkspaceMode);
    setPendingWorkspaceMode(null);
  }, [applyWorkspaceMode, pendingWorkspaceMode]);

  const openVideoPromptConfirm = useCallback(async () => {
    if (!runId) return;
    setVideoPromptStatus(null);
    const shouldLoadSceneRequests = viewKind !== 'scene' || !items.some(isSceneCutItem);
    applyWorkspaceMode('video');
    if (shouldLoadSceneRequests) {
      await loadRunRequests(runId, 'scene');
    }
    setConfirmVideoPromptOpen(true);
  }, [applyWorkspaceMode, items, loadRunRequests, runId, viewKind]);

  const buildVideoGenerateItem = useCallback((item: EditableItem, count = videoCandidateCount): VideoGenerateItemPayload => ({
    item_id: item.id,
    prompt: item.videoDraftPrompt,
    first_reference: item.videoFirstReferencePath || item.selectedCandidatePath || item.existingImage || item.output,
    last_reference: item.videoLastReferencePath,
    references: item.videoReferencePaths,
    quality: item.videoQuality,
    aspect_ratio: item.videoAspectRatio,
    duration_seconds: Math.max(item.videoDurationSec, Math.ceil(item.narrationDurationSec || 0), 1),
    tool: item.videoTool,
    candidate_count: count,
  }), [videoCandidateCount]);

  const generateVideoRequest = useCallback((item: EditableItem) =>
    jsonFetch<CandidatesResponse>('/api/image-gen/video-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        run_id: runId,
        ...buildVideoGenerateItem(item),
      }),
    }), [buildVideoGenerateItem, runId]);

  const generateVideoForCut = useCallback(async (item: EditableItem) => {
    if (!runId) return;
    ensureItemsInState([item]);
    setActiveItemId(item.id);
    setVideoPromptBusy(true);
    setVideoPromptStatus(`動画生成中 ${item.id}`);
    setVideoBulkTotal(1);
    setVideoBulkCompletedCount(0);
    setVideoBulkFailedCount(0);
    patchItem(item.id, { videoGenerating: true, videoCandidates: [] });
    await saveCurrentReview();
    try {
      const data = await generateVideoRequest(item);
      const firstVideoPath = data.candidates.find((candidate) => candidate.path)?.path ?? item.renderVideoPath;
      patchItem(item.id, {
        videoCandidates: data.candidates,
        videoDurationSec: data.durationSeconds ?? item.videoDurationSec,
        renderVideoDurationSec: data.durationSeconds ?? item.renderVideoDurationSec,
        renderVideoPath: firstVideoPath,
        renderVideoExists: Boolean(firstVideoPath),
      });
      const ok = data.candidates.some((candidate) => candidate.path);
      setVideoBulkCompletedCount(ok ? 1 : 0);
      setVideoBulkFailedCount(ok ? 0 : 1);
      setVideoPromptStatus(ok ? `${item.id} 動画生成完了` : `${item.id} 動画生成失敗`);
    } catch (error) {
      console.error(error);
      patchItem(item.id, { videoCandidates: [{ index: 1, status: 'failed', path: null, error: candidateErrorMessage(error) }] });
      setVideoBulkFailedCount(1);
      setVideoPromptStatus(`${item.id} 動画生成失敗`);
    } finally {
      patchItem(item.id, { videoGenerating: false });
      setVideoPromptBusy(false);
    }
  }, [ensureItemsInState, generateVideoRequest, patchItem, runId, saveCurrentReview]);

  const generateVideoItems = useCallback(async (targetItems: EditableItem[]) => {
    if (!runId || !targetItems.length) return;
    ensureItemsInState(targetItems);
    const targetIds = new Set(targetItems.map((item) => item.id));
    const concurrency = Math.min(2, Math.max(targetItems.length, 1));
    setVideoPromptBusy(true);
    setVideoPromptStatus(`動画生成中 0/${targetItems.length}`);
    setVideoBulkTotal(targetItems.length);
    setVideoBulkCompletedCount(0);
    setVideoBulkFailedCount(0);
    setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, videoGenerating: true, videoCandidates: [] } : item)));
    await saveCurrentReview();

    let completed = 0;
    let failed = 0;
    let cursor = 0;
    const runNext = async (): Promise<void> => {
      const item = targetItems[cursor];
      cursor += 1;
      if (!item) return;
      try {
        const data = await generateVideoRequest(item);
        const ok = data.candidates.some((candidate) => candidate.path);
        if (ok) completed += 1;
        else failed += 1;
        setItems((prev) =>
          prev.map((prevItem) =>
            prevItem.id === item.id
              ? {
                  ...prevItem,
                  videoGenerating: false,
                  videoCandidates: data.candidates,
                  videoDurationSec: data.durationSeconds ?? prevItem.videoDurationSec,
                  renderVideoDurationSec: data.durationSeconds ?? prevItem.renderVideoDurationSec,
                  renderVideoPath: data.candidates.find((candidate) => candidate.path)?.path ?? prevItem.renderVideoPath,
                  renderVideoExists: Boolean(data.candidates.find((candidate) => candidate.path)?.path ?? prevItem.renderVideoPath),
                }
              : prevItem,
          ),
        );
      } catch (error) {
        failed += 1;
        setItems((prev) =>
          prev.map((prevItem) =>
            prevItem.id === item.id
              ? {
                  ...prevItem,
                  videoGenerating: false,
                  videoCandidates: [{ index: 1, status: 'failed', path: null, error: candidateErrorMessage(error) }],
                }
              : prevItem,
          ),
        );
      } finally {
        setVideoBulkCompletedCount(completed);
        setVideoBulkFailedCount(failed);
        setVideoPromptStatus(`動画生成中 ${completed + failed}/${targetItems.length}`);
        await runNext();
      }
    };

    try {
      await Promise.all(Array.from({ length: concurrency }, () => runNext()));
      setVideoPromptStatus(`動画生成完了 ${completed}/${targetItems.length}`);
    } finally {
      setVideoPromptBusy(false);
    }
  }, [ensureItemsInState, generateVideoRequest, runId, saveCurrentReview]);

  const generateAllVideos = useCallback(async () => {
    const sceneItems = items.filter(isSceneCutItem);
    if (!sceneItems.length) return;
    setConfirmVideoPromptOpen(false);
    await generateVideoItems(sceneItems);
  }, [generateVideoItems, items]);

  const narrationPayload = useCallback((item: EditableItem) => ({
    item_id: item.id,
    text: item.narrationText,
    tts_text: item.narrationTtsText || item.narrationText,
    output: item.narrationOutput,
    tool: item.narrationTool,
    duration_seconds: Math.max(1, item.renderVideoDurationSec || item.videoDurationSec || 1),
  }), []);

  const applyNarrationResult = useCallback((result: NarrationGenerateResponse['item']) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === result.itemId
          ? {
              ...item,
              narrationGenerating: false,
              narrationExists: result.status === 'completed' || item.narrationExists,
              narrationOutput: result.path || item.narrationOutput,
              renderNarrationPath: result.path || item.renderNarrationPath,
              narrationDurationSec: result.durationSeconds ?? item.narrationDurationSec,
              videoDurationSec: Math.max(item.videoDurationSec, Math.ceil(result.durationSeconds || 0), 1),
              renderVideoDurationSec: Math.max(item.renderVideoDurationSec, Math.ceil(result.durationSeconds || 0), 1),
            }
          : item,
      ),
    );
  }, []);

  const generateNarrationForCut = useCallback(async (item: EditableItem) => {
    if (!runId) return;
    ensureItemsInState([item]);
    setActiveItemId(item.id);
    setNarrationBusy(true);
    setNarrationStatus(`音声生成中 ${item.id}`);
    setNarrationBulkTotal(1);
    setNarrationBulkCompletedCount(0);
    setNarrationBulkFailedCount(0);
    patchItem(item.id, { narrationGenerating: true });
    await saveCurrentReview();
    try {
      const data = await jsonFetch<NarrationGenerateResponse>('/api/image-gen/narration-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, ...narrationPayload(item) }),
      });
      if (data.progress) setRunProgress(data.progress);
      applyNarrationResult(data.item);
      const ok = data.item.status === 'completed';
      setNarrationBulkCompletedCount(ok ? 1 : 0);
      setNarrationBulkFailedCount(ok ? 0 : 1);
      setNarrationStatus(ok ? `${item.id} 音声生成完了` : `${item.id} 音声生成失敗`);
    } catch (error) {
      console.error(error);
      patchItem(item.id, { narrationGenerating: false });
      setNarrationBulkFailedCount(1);
      setNarrationStatus(`${item.id} 音声生成失敗`);
    } finally {
      setNarrationBusy(false);
    }
  }, [applyNarrationResult, ensureItemsInState, narrationPayload, patchItem, runId, saveCurrentReview]);

  const generateAllNarration = useCallback(async () => {
    if (!runId) return;
    const sceneItems = items.filter(isSceneCutItem);
    if (!sceneItems.length) return;
    ensureItemsInState(sceneItems);
    const targetIds = new Set(sceneItems.map((item) => item.id));
    setNarrationBusy(true);
    setNarrationStatus(`音声生成中 0/${sceneItems.length}`);
    setNarrationBulkTotal(sceneItems.length);
    setNarrationBulkCompletedCount(0);
    setNarrationBulkFailedCount(0);
    setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, narrationGenerating: true } : item)));
    await saveCurrentReview();
    try {
      const data = await jsonFetch<BulkNarrationGenerateResponse>('/api/image-gen/narration-generate-bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          items: sceneItems.map((item) => narrationPayload(item)),
          concurrency: 2,
        }),
      });
      if (data.progress) setRunProgress(data.progress);
      let completed = 0;
      let failed = 0;
      data.results.forEach((result) => {
        if (result.status === 'completed') completed += 1;
        else failed += 1;
        applyNarrationResult(result);
      });
      setNarrationBulkCompletedCount(completed);
      setNarrationBulkFailedCount(failed);
      setNarrationStatus(`音声生成完了 ${completed}/${sceneItems.length}`);
    } catch (error) {
      console.error(error);
      setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, narrationGenerating: false } : item)));
      setNarrationBulkFailedCount(sceneItems.length);
      setNarrationStatus('音声生成失敗');
    } finally {
      setNarrationBusy(false);
    }
  }, [applyNarrationResult, ensureItemsInState, items, narrationPayload, runId, saveCurrentReview]);

  const buildRenderItems = useCallback((targetItems: EditableItem[]) => targetItems.map((item) => ({
    item_id: item.id,
    video_path: item.renderVideoPath,
    narration_path: item.renderNarrationPath || item.narrationOutput,
    video_duration_seconds: Math.max(item.renderVideoDurationSec, Math.ceil((item.narrationDurationSec || 0) + item.renderNarrationOffsetSec), 1),
    narration_offset_seconds: item.renderNarrationOffsetSec,
  })), []);

  const freezeRenderInputs = useCallback(async () => {
    if (!runId || !visibleItems.length) return;
    setRenderBusy(true);
    setRenderStatus('レンダー入力を確定中');
    await saveCurrentReview();
    try {
      const data = await jsonFetch<RenderActionResponse>('/api/image-gen/render-inputs/freeze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          items: buildRenderItems(visibleItems),
          output: 'video.mp4',
        }),
      });
      if (data.progress) setRunProgress(data.progress);
      setRenderStatus(data.warnings?.length ? `入力確定 / 警告 ${data.warnings.length}` : 'レンダー入力を確定しました');
    } catch (error) {
      console.error(error);
      setRenderStatus('レンダー入力確定に失敗');
    } finally {
      setRenderBusy(false);
    }
  }, [buildRenderItems, runId, saveCurrentReview, visibleItems]);

  const finalRender = useCallback(async () => {
    if (!runId || !visibleItems.length) return;
    setRenderBusy(true);
    setRenderStatus('最終レンダー中');
    await saveCurrentReview();
    try {
      const data = await jsonFetch<RenderActionResponse>('/api/image-gen/final-render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          items: buildRenderItems(visibleItems),
          output: 'video.mp4',
          reencode: true,
        }),
      });
      if (data.progress) setRunProgress(data.progress);
      setRenderStatus(data.finalOutput ? `最終レンダー完了 ${data.finalOutput}` : '最終レンダー完了');
    } catch (error) {
      console.error(error);
      setRenderStatus('最終レンダー失敗');
    } finally {
      setRenderBusy(false);
    }
  }, [buildRenderItems, runId, saveCurrentReview, visibleItems]);

  const openAddCutDialog = useCallback(() => {
    const defaultAnchor = activeItem?.kind === 'scene' ? activeItem.id : visibleItems[visibleItems.length - 1]?.id || '';
    setAddCutAnchorId(defaultAnchor);
    setAddCutPosition('after');
    setAddCutName('');
    setAddCutError(null);
    setAddCutOpen(true);
  }, [activeItem, visibleItems]);

  const openAddAssetDialog = useCallback(() => {
    setAddAssetType(assetFilter === 'location' ? 'location' : assetFilter === 'obj' ? 'object' : 'character');
    setAddAssetTitle('');
    setAddAssetError(null);
    setAddAssetOpen(true);
  }, [assetFilter]);

  const insertCut = useCallback(async () => {
    if (!runId || !addCutName.trim()) return;
    setAddCutBusy(true);
    setAddCutError(null);
    try {
      const data = await jsonFetch<InsertCutResponse>('/api/image-gen/cuts/insert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          anchor_item_id: addCutAnchorId || null,
          position: addCutPosition,
          cut_name: addCutName.trim(),
        }),
      });
      if (data.progress) setRunProgress(data.progress);
      await loadRunRequests(runId, 'scene');
      setViewKind('scene');
      setActiveItemId(data.selector);
      setRegenerateStatus(`カット追加 ${data.selector}`);
      setAddCutOpen(false);
    } catch (error) {
      console.error(error);
      setAddCutError('カット追加に失敗');
    } finally {
      setAddCutBusy(false);
    }
  }, [addCutAnchorId, addCutName, addCutPosition, loadRunRequests, runId]);

  const createAsset = useCallback(async () => {
    if (!runId || !addAssetTitle.trim()) return;
    const title = addAssetTitle.trim();
    const tempId = `asset_${Date.now()}`;
    const tempItem: EditableItem = {
      id: tempId,
      kind: 'asset',
      assetType: addAssetType,
      tool: 'codex_builtin_image',
      output: null,
      prompt: addAssetDesignPrompt,
      references: [],
      referenceCount: 0,
      executionLane: 'bootstrap_builtin',
      generationStatus: 'prompt_generating',
      existingImage: null,
      draftPrompt: '設計プロンプトを作成中...',
      selectedReferences: [],
      candidates: [],
      selectedCandidatePath: null,
      generating: false,
      promptGenerating: true,
      videoCandidates: [],
      videoGenerating: false,
      videoDraftPrompt: '',
      videoQuality: '1080p',
      videoAspectRatio: '16:9',
      videoDurationSec: 8,
      videoFirstReferencePath: null,
      videoLastReferencePath: null,
      videoReferencePaths: [],
      videoTool: 'kling_3_0',
      sceneKey: null,
      sceneLabel: 'scene',
      narrationText: '',
      narrationTtsText: '',
      narrationOutput: null,
      narrationTool: 'elevenlabs',
      narrationDurationSec: null,
      narrationExists: false,
      narrationGenerating: false,
      renderVideoPath: null,
      renderVideoExists: false,
      renderVideoDurationSec: 8,
      renderNarrationPath: null,
      renderNarrationOffsetSec: 0,
    };
    setAddAssetBusy(true);
    setAddAssetError(null);
    setAddAssetOpen(false);
    setItems((prev) => [...prev, tempItem]);
    setActiveItemId(tempId);
    try {
      const data = await jsonFetch<AssetCreateResponse>('/api/image-gen/assets/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          asset_type: addAssetType,
          title,
        }),
      });
      const created = toEditableItems([data.item], data.references)[0];
      setReferences(data.references);
      setItems((prev) => [...prev.filter((item) => item.id !== tempId), created]);
      setActiveItemId(created.id);
      setAssetFilter(addAssetType === 'character' ? 'chara' : addAssetType === 'object' ? 'obj' : 'location');
      if (data.progress) setRunProgress(data.progress);
      setAddAssetTitle('');
    } catch (error) {
      console.error(error);
      setAddAssetError('アセット追加に失敗');
      setItems((prev) =>
        prev.map((item) =>
          item.id === tempId
            ? { ...item, promptGenerating: false, draftPrompt: 'アセットプロンプト作成に失敗しました。もう一度追加してください。' }
            : item,
        ),
      );
    } finally {
      setAddAssetBusy(false);
    }
  }, [addAssetDesignPrompt, addAssetTitle, addAssetType, runId]);

  const createRun = async () => {
    const title = createRunTitle.trim();
    if (!title) return;
    setCreateRunBusy(true);
    setCreateRunError(null);
    setCreateRunStatus('フォルダを作成中');
    try {
      const created = await jsonFetch<CreateRunJob>('/api/image-gen/runs/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, source: createRunSource.trim() || null }),
      });
      const newRun: RunFolder = {
        id: created.runId,
        name: created.runId,
        path: created.path,
        hasAssetRequests: false,
        hasSceneRequests: false,
      };
      setRuns((prev) => [newRun, ...prev.filter((run) => run.id !== created.runId)]);
      setRunId(created.runId);
      setItems([]);
      setReferences([]);
      setRunProgress(null);
      setCreateRunOpen(false);
      setCreateRunTitle('');
      setCreateRunSource('');
      setCreateRunStatus('ToCを作成中');

      let latest = created;
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await sleep(60000);
        latest = await jsonFetch<CreateRunJob>(`/api/image-gen/runs/create/${encodeURIComponent(created.jobId)}`);
        if (latest.message) setCreateRunStatus(latest.message);
        if (latest.status === 'completed' || latest.status === 'failed') break;
      }
      if (latest.status !== 'completed') {
        throw new Error(latest.error || '作成が完了しませんでした');
      }
      setCreateRunStatus('作成完了');
      await loadRuns(created.runId);
      await loadRunRequests(created.runId, viewKind);
    } catch (error) {
      console.error(error);
      setCreateRunError(error instanceof Error ? error.message : String(error));
      setCreateRunStatus('作成失敗');
      void loadRuns();
    } finally {
      setCreateRunBusy(false);
    }
  };

  const sendChat = async () => {
    if (!chatInput.trim()) return;
    const message = chatInput.trim();
    setChatInput('');
    setChatError(null);
    setChatMessages((prev) => [...prev, { role: 'user', text: message }]);
    setChatBusy(true);
    try {
      const data = await jsonFetch<{ message: string; approvals: unknown[] }>('/api/chat/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          run_id: runId || null,
          session_id: 'image_gen_chat',
          context: activeItem
            ? {
                item_id: activeItem.id,
                output: activeItem.output,
                selected_candidate_path: activeItem.selectedCandidatePath,
              }
            : null,
        }),
      });
      setApprovals(data.approvals);
      setApprovalCount(data.approvals.length);
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', text: data.message || (data.approvals.length ? '承認が必要です。' : '応答がありません。') },
      ]);
    } catch (error) {
      setChatError('送信失敗');
      setChatMessages((prev) => [...prev, { role: 'assistant', text: String(error) }]);
    } finally {
      setChatBusy(false);
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box className="shell">
        <Box className="workspace">
          <AppBar position="static" color="transparent" elevation={0} className="topbar glassTopbar">
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Avatar variant="rounded" className="mark">
                <ImageIcon />
              </Avatar>
              <Box className="topbarTitleBlock">
                <Typography variant="h6">{workspaceModeTitle(workspaceMode)}</Typography>
                <Stack direction="row" spacing={0.75} alignItems="center" className="breadcrumb">
                  <Typography variant="caption">{breadcrumb}</Typography>
                  {runProgress?.currentStage && (
                    <Chip
                      size="small"
                      className="progressMiniChip"
                      label={currentStageCaption(runProgress.currentStage)}
                    />
                  )}
                  <Typography variant="caption" color="text.secondary">
                    {displayedItemCount}件
                  </Typography>
                </Stack>
              </Box>
            </Stack>
            <Stack direction="row" spacing={0.75} alignItems="center" className="topbarActions">
              <FormControl size="small" className="topbarRunSelect">
                <InputLabel>出力先</InputLabel>
                <Select value={runId} label="出力先" onChange={(event) => setRunId(event.target.value)} disabled={generationInFlight}>
                  {runs.map((run) => (
                    <MenuItem key={run.id} value={run.id}>
                      {run.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Tooltip title="新しい出力フォルダを作成">
                <IconButton onClick={() => setCreateRunOpen(true)} color="primary" aria-label="新しい出力フォルダを作成">
                  <AddIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title="出力フォルダを再読み込み">
                <IconButton onClick={() => window.location.reload()} color="primary" aria-label="出力フォルダを再読み込み" disabled={generationInFlight}>
                  <RefreshIcon />
                </IconButton>
              </Tooltip>
            </Stack>
          </AppBar>

          <GlassPanel variant="frosted" density="comfortable" slot="controls" className="controls glassControls">
            <GlassSurface variant="solid" density="compact" slot="controls" className="controlStation repoStation">
              <Typography variant="caption" className="stationLabel">このレポジトリ</Typography>
              <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                <Box minWidth={0}>
                  <Typography fontWeight={800} noWrap>プロンプト正本</Typography>
                  <Typography variant="caption" color="text.secondary" noWrap>
                    全 run 共通の指示を管理
                  </Typography>
                </Box>
                <Tooltip title="全レポジトリ設定を開く">
                  <IconButton onClick={() => setSettingsOpen(true)} color="primary" aria-label="全レポジトリ設定を開く">
                    <SettingsIcon />
                  </IconButton>
                </Tooltip>
              </Stack>
            </GlassSurface>

            <GlassSurface variant="solid" density="compact" slot="controls" className="controlStation targetStation">
              <Typography variant="caption" className="stationLabel">画面</Typography>
              <Tabs value={workspaceMode} onChange={(_, value) => switchWorkspaceMode(value as WorkspaceMode)} className="tabs workspaceTabs">
                <Tab value="image" label="画像" />
                <Tab value="narration" label="音声" />
                <Tab value="video" label="動画" />
                <Tab value="render" label="最終" />
              </Tabs>

              {workspaceMode === 'image' ? (
                <>
                  <Tabs value={viewKind} onChange={(_, value) => setViewKind(value)} className="tabs">
                    <Tab value="asset" label="素材" />
                    <Tab value="scene" label="シーン" />
                  </Tabs>

                  {viewKind === 'asset' && (
                    <Tabs value={assetFilter} onChange={(_, value) => setAssetFilter(value)} className="tabs assetSubTabs">
                      <Tab value="chara" label="キャラクター" />
                      <Tab value="obj" label="アイテム" />
                      <Tab value="location" label="場所" />
                      <Tab value="asset" label="全素材" />
                    </Tabs>
                  )}
                </>
              ) : (
                <Box className="videoModeSummary">
                  {workspaceMode === 'narration' ? <RecordVoiceOverIcon fontSize="small" /> : workspaceMode === 'render' ? <FactCheckIcon fontSize="small" /> : <MovieCreationIcon fontSize="small" />}
                  <Typography variant="body2" fontWeight={800} noWrap>
                    {workspaceMode === 'narration' ? 'シーンcut音声' : workspaceMode === 'render' ? '結合入力' : 'シーンcut動画'}
                  </Typography>
                  <Chip size="small" label={workspaceMode === 'video' ? `${displayedItemCount}/${visibleItems.length} cut` : `${visibleItems.length} cut`} />
                </Box>
              )}
            </GlassSurface>

            <GlassSurface variant="solid" density="compact" slot="controls" className="controlStation countPanel">
              {workspaceMode === 'image' ? (
                <>
                  <Typography variant="caption" className="stationLabel">生成枚数</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography fontWeight={800}>同時生成枚数</Typography>
                    <Chip color="primary" label={`${displayedCandidateCount}候補`} />
                  </Stack>
                  <Slider
                    className="countSlider"
                    min={2}
                    max={16}
                    step={0.1}
                    value={candidateCountDraft}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(value) => `${Math.round(value)}候補`}
                    shiftStep={2}
                    onChange={(_, value) => setCandidateCountDraft(value as number)}
                    onChangeCommitted={(_, value) => {
                      const nextCount = Math.round(value as number);
                      setCandidateCount(nextCount);
                      setCandidateCountDraft(nextCount);
                    }}
                    marks={[
                      { value: 2, label: '2' },
                      { value: 8, label: '8' },
                      { value: 16, label: '16' },
                    ]}
                  />
                </>
              ) : workspaceMode === 'narration' ? (
                <>
                  <Typography variant="caption" className="stationLabel">音声生成</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography fontWeight={800}>全cutナレーション</Typography>
                    <Chip color="primary" label={`${visibleItems.filter((item) => item.narrationExists).length}/${visibleItems.length}`} />
                  </Stack>
                  <Button
                    variant="contained"
                    startIcon={<RecordVoiceOverIcon />}
                    onClick={generateAllNarration}
                    disabled={!visibleItems.length || narrationBusy}
                  >
                    全cut音声生成
                  </Button>
                </>
              ) : workspaceMode === 'render' ? (
                <>
                  <Typography variant="caption" className="stationLabel">最終レンダー</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography fontWeight={800}>結合入力</Typography>
                    <Chip color="primary" label={`${visibleItems.length} cut`} />
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    <Button variant="outlined" startIcon={<FactCheckIcon />} onClick={freezeRenderInputs} disabled={!visibleItems.length || renderBusy}>
                      入力確定
                    </Button>
                    <Button variant="contained" startIcon={<MovieCreationIcon />} onClick={finalRender} disabled={!visibleItems.length || renderBusy}>
                      最終レンダー
                    </Button>
                  </Stack>
                </>
              ) : (
                <>
                  <Typography variant="caption" className="stationLabel">動画生成本数</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography fontWeight={800}>同時生成本数</Typography>
                    <Chip color="primary" label={`${displayedVideoCandidateCount}候補`} />
                  </Stack>
                  <Slider
                    className="countSlider"
                    min={1}
                    max={8}
                    step={0.1}
                    value={videoCandidateCountDraft}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(value) => `${Math.round(value)}本`}
                    shiftStep={1}
                    onChange={(_, value) => setVideoCandidateCountDraft(value as number)}
                    onChangeCommitted={(_, value) => {
                      const nextCount = Math.round(value as number);
                      setVideoCandidateCount(nextCount);
                      setVideoCandidateCountDraft(nextCount);
                    }}
                    marks={[
                      { value: 1, label: '1' },
                      { value: 3, label: '3' },
                      { value: 8, label: '8' },
                    ]}
                  />
                  <Button
                    variant="contained"
                    startIcon={<MovieCreationIcon />}
                    onClick={openVideoPromptConfirm}
                    disabled={!visibleItems.length || videoPromptBusy}
                  >
                    全cut動画生成
                  </Button>
                </>
              )}
            </GlassSurface>
          </GlassPanel>

          {(createRunStatus || createRunError) && (
            <Stack direction="row" spacing={1} alignItems="center" className="createRunStatusBar">
              {createRunBusy && <LinearProgress className="createRunStatusProgress" />}
              {createRunStatus && <Chip size="small" color={createRunBusy ? 'primary' : 'default'} label={createRunStatus} />}
              {createRunError && <Chip size="small" color="error" label={createRunError} />}
            </Stack>
          )}

          {busy && <LinearProgress />}
          <Box className="gridScroll">
            {workspaceMode === 'image' ? (
              <Box className="promptGrid">
                {!busy && !items.length && (
                  <GlassPanel variant="frosted" density="spacious" className="emptyGallery">
                    <Typography fontWeight={900}>画像生成データはまだありません</Typography>
                    <Typography variant="body2" color="text.secondary">
                      この run はレポ作成中、または画像生成 request の作成前です。表示中の p は完了済みではなく、次に作る成果物の位置です。
                    </Typography>
                    <RunProgressPanel progress={runProgress} />
                  </GlassPanel>
                )}
                {!busy && Boolean(items.length) && !visibleItems.length && (
                  <GlassPanel variant="frosted" density="spacious" className="emptyGallery">
                    <Typography fontWeight={900}>このカテゴリは空です</Typography>
                    <Typography variant="body2" color="text.secondary">
                      素材側はキャラクター / アイテム / 場所 / 全素材の順に整理されています。別カテゴリへ切り替えてください。
                    </Typography>
                  </GlassPanel>
                )}
                {visibleItems.map((item) => (
                  <PromptCard
                    key={item.id}
                    item={item}
                    runId={runId}
                    viewKind={viewKind}
                    references={references}
                    candidateCount={candidateCount}
                    adoptedKeys={adoptedKeys}
                    onPatchItem={patchItem}
                    onGenerateItem={generateItem}
                    onSetActiveItemId={setActiveItemIdStable}
                    onOpenImage={openEnlargedImage}
                  />
                ))}
                {!busy && viewKind === 'asset' && Boolean(runId) && (
                  <GlassPanel variant="frosted" density="spacious" className="addCutCard">
                    <AddCircleOutlineIcon className="addCutIcon" />
                    <Typography fontWeight={900}>アセットを追加</Typography>
                    <Typography variant="body2" color="text.secondary">
                      種類とタイトルから設計プロンプトを作り、素材requestへ追加します。
                    </Typography>
                    <Button variant="outlined" startIcon={<AddIcon />} onClick={openAddAssetDialog} disabled={addAssetBusy}>
                      アセット追加
                    </Button>
                  </GlassPanel>
                )}
                {!busy && viewKind === 'scene' && Boolean(runId) && Boolean(visibleItems.length) && (
                  <GlassPanel variant="frosted" density="spacious" className="addCutCard">
                    <AddCircleOutlineIcon className="addCutIcon" />
                    <Typography fontWeight={900}>カットを追加</Typography>
                    <Typography variant="body2" color="text.secondary">
                      既存sceneの前後位置を選び、manifestと画像requestへ差し込みます。
                    </Typography>
                    <Button variant="outlined" startIcon={<AddIcon />} onClick={openAddCutDialog}>
                      カット追加
                    </Button>
                  </GlassPanel>
                )}
              </Box>
            ) : (
              <Box className="videoCutGrid">
                {workspaceMode === 'video' && videoSceneGroups.length > 0 && (
                  <Box className="sceneCutTabsBar">
                    <Tabs
                      value={activeVideoScene?.key || ''}
                      onChange={(_, value) => setActiveVideoSceneKey(value as string)}
                      className="tabs sceneCutTabs"
                      variant="scrollable"
                      scrollButtons="auto"
                    >
                      {videoSceneGroups.map((group) => (
                        <Tab key={group.key} value={group.key} label={`${group.label} / ${group.items.length}`} />
                      ))}
                    </Tabs>
                    <Chip size="small" color="primary" label={`${videoDisplayItems.length}/${visibleItems.length} cut`} />
                  </Box>
                )}
                {!busy && !items.length && (
                  <GlassPanel variant="frosted" density="spacious" className="emptyGallery">
                    <Typography fontWeight={900}>シーンcutはまだありません</Typography>
                    <RunProgressPanel progress={runProgress} />
                  </GlassPanel>
                )}
                {!busy && Boolean(items.length) && !visibleItems.length && (
                  <GlassPanel variant="frosted" density="spacious" className="emptyGallery">
                    <Typography fontWeight={900}>表示できるシーンcutがありません</Typography>
                  </GlassPanel>
                )}
                {workspaceMode === 'narration' && visibleItems.map((item) => (
                  <NarrationCutCard
                    key={item.id}
                    item={item}
                    runId={runId}
                    narrationBusy={narrationBusy}
                    onPatchItem={patchItem}
                    onGenerateNarration={generateNarrationForCut}
                  />
                ))}
                {workspaceMode === 'video' && videoDisplayItems.map((item) => (
                  <VideoCutCard
                    key={item.id}
                    item={item}
                    runId={runId}
                    references={references}
                    videoGenerationBusy={videoPromptBusy}
                    videoCandidateCount={videoCandidateCount}
                    onPatchItem={patchItem}
                    onGenerateVideo={generateVideoForCut}
                  />
                ))}
                {workspaceMode === 'render' && visibleItems.map((item) => (
                  <RenderCutCard
                    key={item.id}
                    item={item}
                    runId={runId}
                    onPatchItem={patchItem}
                  />
                ))}
              </Box>
            )}
          </Box>

          <GlassDock edge="bottom" variant="frosted" density="compact" slot="footer" className="bulkFooter">
            <Stack direction="row" spacing={1} alignItems="center" minWidth={0}>
              {workspaceMode === 'image' && <Chip size="small" color={selectedForInsert.length ? 'primary' : 'default'} label={`${selectedForInsert.length}件採用候補`} />}
              {workspaceMode === 'image' && bulkGenerating && <Chip size="small" color="primary" label={`生成中 ${bulkCompletedCount + bulkFailedCount}/${bulkTotal}`} />}
              {workspaceMode === 'image' && !bulkGenerating && bulkTotal > 0 && <Chip size="small" label={`生成完了 ${bulkCompletedCount + bulkFailedCount}/${bulkTotal}`} />}
              {workspaceMode === 'image' && bulkFailedCount > 0 && <Chip size="small" color="error" label={`失敗 ${bulkFailedCount}`} />}
              {workspaceMode === 'image' && insertStatus === 'running' && <Chip size="small" color="primary" label="挿入中" />}
              {workspaceMode === 'image' && insertStatus === 'success' && <Chip size="small" color="success" label={`${lastInsertedCount}件 挿入済み`} />}
              {workspaceMode === 'image' && insertStatus === 'error' && <Chip size="small" color="error" label="挿入失敗" />}
              {workspaceMode === 'image' && addAssetBusy && <Chip size="small" color="primary" label="アセット作成中" />}
              {workspaceMode === 'image' && addAssetError && <Chip size="small" color="error" label={addAssetError} />}
              {workspaceMode === 'image' && downloadError && <Chip size="small" color="error" label={downloadError} />}
              {workspaceMode === 'video' && videoPromptBusy && <Chip size="small" color="primary" label={`動画生成中 ${videoBulkCompletedCount + videoBulkFailedCount}/${videoBulkTotal || visibleItems.length}`} />}
              {workspaceMode === 'video' && !videoPromptBusy && videoBulkTotal > 0 && <Chip size="small" label={`動画生成完了 ${videoBulkCompletedCount + videoBulkFailedCount}/${videoBulkTotal}`} />}
              {workspaceMode === 'video' && videoBulkFailedCount > 0 && <Chip size="small" color="error" label={`動画失敗 ${videoBulkFailedCount}`} />}
              {workspaceMode === 'narration' && narrationBusy && <Chip size="small" color="primary" label={`音声生成中 ${narrationBulkCompletedCount + narrationBulkFailedCount}/${narrationBulkTotal || visibleItems.length}`} />}
              {workspaceMode === 'narration' && !narrationBusy && narrationBulkTotal > 0 && <Chip size="small" label={`音声生成完了 ${narrationBulkCompletedCount + narrationBulkFailedCount}/${narrationBulkTotal}`} />}
              {workspaceMode === 'narration' && narrationBulkFailedCount > 0 && <Chip size="small" color="error" label={`音声失敗 ${narrationBulkFailedCount}`} />}
              {workspaceMode === 'render' && renderBusy && <Chip size="small" color="primary" label={renderStatus || 'レンダー処理中'} />}
              {backgroundGenerationLabel && <Chip size="small" color="secondary" label={backgroundGenerationLabel} />}
              {regenerateStatus && <Chip size="small" color={regenerateBusy ? 'primary' : 'default'} label={regenerateStatus} />}
              {reviewSaveStatus && <Chip size="small" color={reviewSaveBusy ? 'primary' : reviewSaveStatus.includes('失敗') ? 'error' : 'default'} label={reviewSaveStatus} />}
              {videoPromptStatus && <Chip size="small" color={videoPromptBusy ? 'primary' : videoPromptStatus.includes('失敗') ? 'error' : 'default'} label={videoPromptStatus} />}
              {narrationStatus && <Chip size="small" color={narrationBusy ? 'primary' : narrationStatus.includes('失敗') ? 'error' : 'default'} label={narrationStatus} />}
              {renderStatus && !renderBusy && <Chip size="small" color={renderStatus.includes('失敗') ? 'error' : 'default'} label={renderStatus} />}
              {addCutError && <Chip size="small" color="error" label={addCutError} />}
              <Typography variant="caption" color="text.secondary" noWrap>
                {selectedRun?.path || '出力先未選択'}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button variant="outlined" startIcon={<SaveIcon />} onClick={saveCurrentReview} disabled={!visibleItems.length || reviewSaveBusy}>
                一時保存
              </Button>
              {workspaceMode === 'image' ? (
                <>
                  <Button variant="contained" startIcon={<AutoAwesomeIcon />} onClick={generateBulk} disabled={!visibleItems.length || bulkGenerating}>
                    一括生成
                  </Button>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={downloadZip}>
                    一括ダウンロード
                  </Button>
                  <Button className="insertAction" variant="contained" startIcon={<SaveAltIcon />} onClick={insertBulk} disabled={!selectedForInsert.length || insertBusy}>
                    リポジトリへ挿入
                  </Button>
                </>
              ) : workspaceMode === 'narration' ? (
                <Button
                  className="insertAction"
                  variant="contained"
                  startIcon={<RecordVoiceOverIcon />}
                  onClick={generateAllNarration}
                  disabled={!visibleItems.length || narrationBusy}
                >
                  全cut音声生成
                </Button>
              ) : workspaceMode === 'render' ? (
                <>
                  <Button variant="outlined" startIcon={<FactCheckIcon />} onClick={freezeRenderInputs} disabled={!visibleItems.length || renderBusy}>
                    入力確定
                  </Button>
                  <Button className="insertAction" variant="contained" startIcon={<MovieCreationIcon />} onClick={finalRender} disabled={!visibleItems.length || renderBusy}>
                    最終レンダー
                  </Button>
                </>
              ) : (
                <Button
                  className="insertAction"
                  variant="contained"
                  startIcon={<MovieCreationIcon />}
                  onClick={openVideoPromptConfirm}
                  disabled={!visibleItems.length || videoPromptBusy}
                >
                  全cut動画生成
                </Button>
              )}
              <Tooltip title="制作相談を開く">
                <IconButton
                  ref={mobileChatButtonRef}
                  className="mobileChatButton"
                  color="secondary"
                  onClick={() => setChatOpen(true)}
                  aria-label="制作相談を開く"
                >
                  <ChatIcon />
                </IconButton>
              </Tooltip>
            </Stack>
          </GlassDock>
        </Box>

        <Dialog
          open={Boolean(pendingWorkspaceMode)}
          onClose={() => setPendingWorkspaceMode(null)}
          className="settingsDialog"
          aria-labelledby="confirm-workspace-switch-title"
        >
          <DialogTitle id="confirm-workspace-switch-title">生成中の画面を離れますか？</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={1.5}>
              <Typography>
                現在の生成はサーバー側で継続します。別画面へ移動しても、下部ステータスと進捗 polling は維持されます。
              </Typography>
              <Typography variant="body2" color="text.secondary">
                戻ると生成中のカード表示と、完了または失敗した候補が反映されます。
              </Typography>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPendingWorkspaceMode(null)}>この画面に残る</Button>
            <Button variant="contained" onClick={confirmWorkspaceSwitch}>移動する</Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={createRunOpen}
          onClose={() => setCreateRunOpen(false)}
          fullWidth
          maxWidth="sm"
          className="settingsDialog createRunDialog"
          aria-labelledby="create-run-title"
        >
          <DialogTitle id="create-run-title">新しいToCを作成</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <TextField
                label="タイトル"
                value={createRunTitle}
                disabled={createRunBusy}
                onChange={(event) => setCreateRunTitle(event.target.value)}
                autoFocus
                fullWidth
              />
              <TextField
                label="中身"
                value={createRunSource}
                disabled={createRunBusy}
                onChange={(event) => setCreateRunSource(event.target.value)}
                placeholder="空欄の場合はタイトルと同じ内容で作成"
                multiline
                minRows={5}
                fullWidth
              />
              {createRunBusy && <LinearProgress />}
              <Box className="createRunStatusRow">
                {createRunStatus && <Chip size="small" color={createRunBusy ? 'primary' : 'default'} label={createRunStatus} />}
                {createRunError && <Chip size="small" color="error" label="作成失敗" />}
              </Box>
              {createRunError && (
                <Typography variant="body2" color="error" whiteSpace="pre-wrap">
                  {createRunError}
                </Typography>
              )}
            </Stack>
          </DialogContent>
          <DialogActions className="settingsActions">
            <Button onClick={() => setCreateRunOpen(false)}>{createRunBusy ? '閉じる' : 'キャンセル'}</Button>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={createRun}
              disabled={createRunBusy || !createRunTitle.trim()}
            >
              作成
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          fullWidth
          maxWidth="lg"
          fullScreen={isNarrowViewport}
          className="settingsDialog"
          aria-labelledby="prompt-settings-title"
        >
          <DialogTitle id="prompt-settings-title">全レポジトリ設定</DialogTitle>
          <DialogContent dividers>
            <Tabs value={settingsTarget} onChange={(_, value) => setSettingsTarget(value)} className="settingsTabs">
              <Tab value="character" label="キャラクター" />
              <Tab value="item" label="アイテム" />
              <Tab value="location" label="場所" />
              <Tab value="scene" label="シーン" />
            </Tabs>
            <Box className="settingsStatusRow">
              <Chip size="small" label={settingsTargetLabel(settingsTarget)} color="primary" />
              {settingPath && <Typography variant="caption" color="text.secondary" noWrap>{settingPath}</Typography>}
              {settingsBusy && <Chip size="small" label="処理中" />}
              {settingsError && <Chip size="small" color="error" label={settingsError} />}
            </Box>
            <Box className="settingsSplit">
              <Box className="settingsSourcePane">
                <Typography variant="caption" color="text.secondary">現在の正本設定</Typography>
                {settingsBusy ? (
                  <LinearProgress />
                ) : (
                  <TextField
                    className="settingsTextArea"
                    multiline
                    minRows={18}
                    value={settingContent}
                    InputProps={{ readOnly: true }}
                  />
                )}
              </Box>
              <Box className="settingsDraftPane">
                <Typography variant="caption" color="text.secondary">新しい指示</Typography>
                <TextField
                  className="settingsTextArea"
                  multiline
                  minRows={18}
                  placeholder="ここに新しいプロンプト指示を書いてください"
                  value={settingDraft}
                  onChange={(event) => setSettingDraft(event.target.value)}
                />
              </Box>
            </Box>
          </DialogContent>
          <DialogActions className="settingsActions">
            <Button onClick={() => setSettingsOpen(false)}>閉じる</Button>
            <Button
              variant="outlined"
              onClick={savePermanentSetting}
              disabled={settingsBusy || !settingDraft.trim()}
            >
              恒常変更
            </Button>
            <Button
              variant="contained"
              startIcon={<AutoAwesomeIcon />}
              onClick={openRegenerateConfirm}
              disabled={settingsBusy || regenerateBusy || !settingDraft.trim() || !runId}
            >
              新しいプロンプトで再度プロンプトを生成
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={confirmRegenerateOpen}
          onClose={() => setConfirmRegenerateOpen(false)}
          className="settingsDialog"
          aria-labelledby="confirm-regenerate-title"
        >
          <DialogTitle id="confirm-regenerate-title">プロンプトを再生成しますか？</DialogTitle>
          <DialogContent dividers>
            <Typography>
              {currentSettingsTarget === settingsTarget
                ? `${settingsTargetLabel(settingsTarget)}の表示中 ${visibleItems.filter((item) => item.executionLane !== 'existing_asset').length} 件を、新しい指示で再生成します。`
                : `${settingsTargetLabel(settingsTarget)}タブの対象を、新しい指示で再生成します。`}
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmRegenerateOpen(false)}>キャンセル</Button>
            <Button variant="contained" onClick={regeneratePrompts}>OK</Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={confirmImageGenerateOpen}
          onClose={() => setConfirmImageGenerateOpen(false)}
          className="settingsDialog"
          aria-labelledby="confirm-image-generate-title"
        >
          <DialogTitle id="confirm-image-generate-title">新しいプロンプトで画像を生成しますか？</DialogTitle>
          <DialogContent dividers>
            <Typography>
              更新された {regeneratedItems.length} 件について、現在の同時生成枚数 {candidateCount} 候補で画像生成します。
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmImageGenerateOpen(false)}>いいえ</Button>
            <Button variant="contained" startIcon={<AutoAwesomeIcon />} onClick={generateRegeneratedImages}>
              はい
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={confirmVideoPromptOpen}
          onClose={() => setConfirmVideoPromptOpen(false)}
          className="settingsDialog"
          aria-labelledby="confirm-video-prompt-title"
        >
          <DialogTitle id="confirm-video-prompt-title">全cutの動画を生成しますか？</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={1.5}>
              <Typography>
                現在の動画レビューを一時保存してから、各cutの設定で実動画APIを呼び出します。
              </Typography>
              <Typography variant="body2" color="text.secondary">
                対象: {items.filter(isSceneCutItem).length} cut / 各cut {videoCandidateCount} 本を候補動画として並列生成します。
              </Typography>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmVideoPromptOpen(false)}>キャンセル</Button>
            <Button variant="contained" startIcon={<MovieCreationIcon />} onClick={generateAllVideos} disabled={videoPromptBusy || !items.some(isSceneCutItem)}>
              全cut動画生成
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={addAssetOpen}
          onClose={() => setAddAssetOpen(false)}
          fullWidth
          maxWidth="md"
          className="settingsDialog"
          aria-labelledby="add-asset-title"
        >
          <DialogTitle id="add-asset-title">アセットを追加</DialogTitle>
          <DialogContent dividers>
            <Box className="settingsSplit">
              <Stack spacing={2} className="settingsDraftPane">
                <FormControl fullWidth size="small">
                  <InputLabel>アセット種類</InputLabel>
                  <Select
                    label="アセット種類"
                    value={addAssetType}
                    onChange={(event) => setAddAssetType(event.target.value as AssetCreateType)}
                  >
                    <MenuItem value="character">キャラクター</MenuItem>
                    <MenuItem value="object">アイテム</MenuItem>
                    <MenuItem value="location">場所</MenuItem>
                  </Select>
                </FormControl>
                <TextField
                  label="タイトル"
                  value={addAssetTitle}
                  onChange={(event) => setAddAssetTitle(event.target.value)}
                  placeholder={`${assetCreateTypeLabel(addAssetType)}名`}
                  autoFocus
                  fullWidth
                />
                {addAssetError && <Typography color="error">{addAssetError}</Typography>}
              </Stack>
              <Box className="settingsSourcePane">
                <Typography variant="caption" color="text.secondary">asset作成時の設計プロンプト</Typography>
                <TextField
                  className="settingsTextArea"
                  multiline
                  minRows={12}
                  value={addAssetDesignPrompt}
                  InputProps={{ readOnly: true }}
                />
              </Box>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAddAssetOpen(false)}>キャンセル</Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={createAsset} disabled={addAssetBusy || !addAssetTitle.trim()}>
              作成
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={addCutOpen}
          onClose={() => setAddCutOpen(false)}
          fullWidth
          maxWidth="sm"
          className="settingsDialog"
          aria-labelledby="add-cut-title"
        >
          <DialogTitle id="add-cut-title">カットを追加</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <FormControl fullWidth size="small">
                <InputLabel>挿入位置の基準</InputLabel>
                <Select
                  label="挿入位置の基準"
                  value={addCutAnchorId}
                  onChange={(event) => setAddCutAnchorId(event.target.value)}
                >
                  {visibleItems.map((item) => (
                    <MenuItem key={item.id} value={item.id}>
                      {item.id}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth size="small">
                <InputLabel>位置</InputLabel>
                <Select
                  label="位置"
                  value={addCutPosition}
                  onChange={(event) => setAddCutPosition(event.target.value as 'before' | 'after' | 'end')}
                >
                  <MenuItem value="after">基準cutの後</MenuItem>
                  <MenuItem value="before">基準cutの前</MenuItem>
                  <MenuItem value="end">sceneの最後</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="カット名"
                value={addCutName}
                onChange={(event) => setAddCutName(event.target.value)}
                placeholder="例: 視線のつなぎ / 扉へ近づく"
                autoFocus
                fullWidth
              />
              {addCutBusy && <LinearProgress />}
              {addCutError && <Typography color="error">{addCutError}</Typography>}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAddCutOpen(false)}>キャンセル</Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={insertCut} disabled={addCutBusy || !addCutName.trim() || (!addCutAnchorId && addCutPosition !== 'end')}>
              追加
            </Button>
          </DialogActions>
        </Dialog>

        <Dialog
          open={Boolean(enlargedImage)}
          onClose={closeEnlargedImage}
          fullWidth
          maxWidth="xl"
          className="imageEnlargeDialog"
          aria-labelledby="image-enlarge-title"
        >
          <DialogTitle id="image-enlarge-title" className="imageEnlargeTitle">
            <Box minWidth={0}>
              <Typography fontWeight={900} noWrap>
                {enlargedImage?.itemId}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {enlargedImage ? `${enlargedImage.label} / ${enlargedImage.path}` : ''}
              </Typography>
            </Box>
            <Button onClick={closeEnlargedImage}>閉じる</Button>
          </DialogTitle>
          <DialogContent dividers className="imageEnlargeContent">
            {enlargedImage && (
              <img
                src={enlargedImage.src}
                alt={`${enlargedImage.itemId} ${enlargedImage.label}`}
                className="imageEnlargePreview"
              />
            )}
          </DialogContent>
          <DialogActions>
            <Button variant="contained" onClick={closeEnlargedImage}>
              閉じる
            </Button>
          </DialogActions>
        </Dialog>

        {chatOpen && <Box className="chatBackdrop" onClick={closeChat} />}
        <GlassPanel
          variant="frosted"
          tone="secondary"
          density="compact"
          slot="chat"
          className={`chatPane ${chatOpen ? 'is-open' : ''}`}
          aria-hidden={isNarrowViewport && !chatOpen ? true : undefined}
          inert={isNarrowViewport && !chatOpen ? true : undefined}
        >
          <GlassSurface variant="frosted" tone="secondary" density="compact" slot="chat" className="chatHead">
            <Stack direction="row" alignItems="center" spacing={1}>
            <Avatar variant="rounded" className="chatMark">
              <ArchiveIcon />
            </Avatar>
            <Box>
              <Typography fontWeight={900}>制作相談</Typography>
              <Typography variant="caption" color="text.secondary">
                {selectedRun?.name || '出力先未選択'} / {breadcrumb}
              </Typography>
              <Typography variant="caption" color="text.secondary" className="chatItemContext">
                {activeItem ? `${activeItem.id} / ${activeItem.selectedCandidatePath ? '採用候補あり' : activeItem.output || '出力先未設定'}` : '対象未選択'}
              </Typography>
            </Box>
            </Stack>
            <IconButton className="chatClose" size="small" onClick={closeChat} aria-label="制作相談を閉じる">
              ×
            </IconButton>
          </GlassSurface>
          <Stack direction="row" spacing={1} className="chatStatus">
            <Chip size="small" color={chatBusy ? 'primary' : 'default'} label={chatBusy ? '応答待ち' : '待機中'} />
            {approvalCount > 0 && <Chip size="small" color="warning" label={`承認待ち ${approvalCount}件`} />}
            {chatError && <Chip size="small" color="error" label={chatError} />}
          </Stack>
          {approvals.length > 0 && (
            <Box className="approvalBlock" aria-label="承認待ち一覧">
              <Typography variant="caption" fontWeight={900}>承認待ち</Typography>
              {approvals.slice(0, 3).map((approval, index) => (
                <Typography key={index} variant="caption" color="text.secondary" noWrap>
                  {typeof approval === 'string' ? approval : JSON.stringify(approval)}
                </Typography>
              ))}
            </Box>
          )}
          <Divider />
          <Box className="messages">
            {chatMessages.map((message, index) => (
              <Box key={index} className={`bubble ${message.role}`}>
                <Typography whiteSpace="pre-wrap">{message.text}</Typography>
              </Box>
            ))}
            {chatBusy && <LinearProgress />}
          </Box>
          <Stack direction="row" spacing={1} className="composer">
            <TextField
              fullWidth
              size="small"
              placeholder="画像生成プロンプトや参照設定を相談"
              inputRef={chatInputRef}
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void sendChat();
                }
              }}
            />
            <IconButton color="primary" onClick={sendChat} disabled={chatBusy} aria-label="相談を送信">
              <SendIcon />
            </IconButton>
          </Stack>
        </GlassPanel>
      </Box>
    </ThemeProvider>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
