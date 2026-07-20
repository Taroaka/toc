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
import KeyboardArrowLeftIcon from '@mui/icons-material/KeyboardArrowLeft';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import MovieCreationIcon from '@mui/icons-material/MovieCreation';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import SendIcon from '@mui/icons-material/Send';
import SaveIcon from '@mui/icons-material/Save';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import RefreshIcon from '@mui/icons-material/Refresh';
import SettingsIcon from '@mui/icons-material/Settings';
import StopIcon from '@mui/icons-material/Stop';
import { GlassDock, GlassPanel, GlassStatusRim, GlassSurface } from './components';
import './styles.css';

const MAX_CUT_VIDEO_DURATION_SECONDS = 60;

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
  promptPolicyVersion?: string | null;
  debugPromptSource?: Record<string, unknown>;
  legacyPrompt?: string | null;
  references: string[];
  referenceCount: number;
  executionLane: string;
  generationStatus: string | null;
  existingImage: string | null;
  candidates?: Candidate[];
  sceneId?: string | null;
  isRenderUnit?: boolean;
  sourceCutIds?: string[];
  videoPrompt?: string;
  videoOutput?: string | null;
  selectedVideoPath?: string | null;
  videoExists?: boolean;
  videoDurationSeconds?: number | null;
  configuredVideoDurationSeconds?: number;
  videoTool?: string;
  videoQuality?: string;
  videoAspectRatio?: string;
  videoInputMode?: string;
  videoFirstReference?: string;
  videoLastReference?: string;
  videoReferences?: string[];
};

type ReferenceOption = {
  path: string;
  label: string;
  available?: boolean;
};

type Candidate = {
  index: number;
  status: string;
  path: string | null;
  error?: string;
  revisedPrompt?: string | null;
  mtimeMs?: number;
};

const VIDEO_DRAFT_FIELDS = [
  'videoDraftPrompt',
  'videoQuality',
  'videoAspectRatio',
  'videoDurationSec',
  'videoFirstReferencePath',
  'videoLastReferencePath',
  'videoReferencePaths',
  'videoTool',
] as const;

type VideoDraftField = (typeof VIDEO_DRAFT_FIELDS)[number];
const VIDEO_DRAFT_FIELD_SET = new Set<string>(VIDEO_DRAFT_FIELDS);

type EditableItem = ImageRequestItem & {
  draftPrompt: string;
  selectedReferences: ReferenceOption[];
  candidates: Candidate[];
  selectedCandidatePath: string | null;
  generating: boolean;
  generationJobStatus?: 'queued' | 'running' | 'completed' | 'failed' | 'blocked';
  generationGroupIndex?: number | null;
  promptGenerating?: boolean;
  videoCandidates: Candidate[];
  videoGenerating: boolean;
  videoDirtyFields: VideoDraftField[];
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
  narrationStatus: string;
  narrationReviewStatus: string;
  narrationAuthoringStatus: string;
  narrationRevision: number;
  narrationTextHash: string;
  narrationTtsHash: string;
  narrationGenerationStatus: string;
  narrationCandidateId: string | null;
  narrationCandidateOutput: string | null;
  narrationCandidateStatus: string;
  narrationCandidateExists: boolean;
  narrationCandidateDurationSec: number | null;
  narrationGeneratedFromTtsHash: string;
  narrationAudioReviewStatus: string;
  narrationAudioHumanApproved: boolean;
  narrationDirty: boolean;
  narrationSaving: boolean;
  narrationApproving: boolean;
  narrationSilentOk: boolean;
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
  promptPolicyVersion?: string;
  operation: 'direct_update' | 'recompiled';
  requestRevision?: string;
  sourceDigest?: string;
  compilerVersion?: string;
};

type RegeneratePromptsResponse = {
  status: string;
  operation: 'direct_update' | 'recompiled';
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
  narrationStatus: string;
  narrationReviewStatus: string;
  narrationAuthoringStatus: string;
  narrationRevision: number;
  narrationTextHash: string;
  narrationTtsHash: string;
  narrationGenerationStatus: string;
  narrationCandidateId: string | null;
  narrationCandidateOutput: string | null;
  narrationCandidateStatus: string;
  narrationCandidateExists: boolean;
  narrationCandidateDurationSeconds: number | null;
  narrationGeneratedFromTtsHash: string;
  narrationAudioReviewStatus: string;
  narrationAudioHumanApproved: boolean;
  narrationSilentOk: boolean;
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
    candidateId?: string;
    generatedFromTtsHash?: string;
    requestRevision?: number;
    error?: string;
  };
  progress?: RunProgress;
};

type NarrationDraftCreateResponse = {
  status: string;
  updated: string[];
  skipped: string[];
  reportPath: string;
  authoringWorkspace?: {
    status: string;
    audioStoryPath?: string;
    authoringPromptPath?: string;
    warning?: string;
  };
  progress?: RunProgress;
};

type NarrationSilentOkResponse = {
  status: string;
  itemId: string;
  audioSetHash: string;
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

type CreateRunMode = 'normal' | 'scene_storyboard';

type CreateRunJob = {
  jobId: string;
  runId: string;
  path: string;
  status: 'running' | 'completed' | 'failed' | 'paused';
  title: string;
  createMode?: CreateRunMode;
  targetDurationSeconds?: number;
  stopTargetNumber?: number;
  currentProcess?: string;
  currentProcessNumber?: number;
  pid?: number | null;
  message?: string | null;
  error?: string | null;
  errorCode?: string | null;
};

type CandidatesResponse = {
  itemId: string;
  candidates: Candidate[];
  error?: string;
  durationSeconds?: number;
  minDurationSeconds?: number | null;
};

type BulkGenerationJobResult = {
  itemId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'blocked';
  groupIndex: number;
  candidates: Candidate[];
  error?: string;
};

type BulkGenerationJob = {
  jobId: string;
  runId: string;
  kind: 'asset' | 'scene';
  status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted';
  totalCount: number;
  completedCount: number;
  failedCount: number;
  currentGroup: number | null;
  groupCount: number;
  results: BulkGenerationJobResult[];
  error?: string | null;
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

type NarrationRevisionSummary = {
  number: number;
  text_hash: string;
  tts_hash: string;
};

type NarrationWorkflowItem = {
  itemId: string;
  authoringStatus: string;
  status: string;
  text: string;
  ttsText: string;
  tool: string;
  output: string | null;
  revision: NarrationRevisionSummary;
  generation: { status?: string; candidate_id?: string; generated_from_tts_hash?: string };
  audioReview: { status?: string };
  candidate?: {
    candidate_id?: string;
    output?: string;
    status?: string;
    duration_seconds?: number | null;
    generated_from_tts_hash?: string;
  } | null;
  approvedCandidate?: {
    candidate_id?: string;
    output?: string;
    status?: string;
    duration_seconds?: number | null;
    generated_from_tts_hash?: string;
  } | null;
};

type NarrationTextSaveResponse = {
  status: string;
  item: NarrationWorkflowItem;
  audioSetHash: string;
  progress?: RunProgress;
};

type NarrationAudioApproveResponse = {
  status: string;
  item: NarrationWorkflowItem;
  durationUpdated: string[];
  audioSetHash: string;
  progress?: RunProgress;
};

type NarrationRunApproveResponse = {
  status: string;
  approvedAudioSetHash: string;
  approvedTimelineHash: string;
  progress?: RunProgress;
};

type NarrationTimelinePayload = {
  item_id: string;
  video_duration_seconds: number;
  narration_offset_seconds: number;
};

type NarrationListenEvidence = {
  mode: 'sequential_full_run';
  audio_set_hash: string;
  item_ids: string[];
  timeline: NarrationTimelinePayload[];
  completed_at: string;
};

type NarrationReviewRunResponse = {
  status: string;
  findings: string[];
  arcFindings: string[];
  cutFindings: Array<{ itemId: string; reasonKeys: string[]; messages: string[] }>;
  semanticFindings: Array<{ critic_id?: string; critic_label?: string; severity?: string; message?: string }>;
  narrationTextSetHash: string;
  report: string;
  arcReport: string;
  semanticReport: string;
  progress?: RunProgress;
};

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

function imageRequestScopeKey(runId: string, kind: ViewKind): string {
  return `${runId}\u0000${kind}`;
}

function mergeCandidateSnapshots(previous: Candidate[], incoming: Candidate[]): Candidate[] {
  const mergedByIndex = new Map<number, Candidate>();
  const incomingPathIndexes = new Map<string, number>();

  incoming.forEach((candidate) => {
    if (candidate.path) {
      const duplicateIndex = incomingPathIndexes.get(candidate.path);
      if (duplicateIndex !== undefined && duplicateIndex !== candidate.index) {
        mergedByIndex.delete(duplicateIndex);
      }
      incomingPathIndexes.set(candidate.path, candidate.index);
    }
    mergedByIndex.set(candidate.index, candidate);
  });

  previous.forEach((candidate) => {
    if (!candidate.path) return;
    const samePath = Array.from(mergedByIndex.values()).find((current) => current.path === candidate.path);
    if (samePath) return;
    const current = mergedByIndex.get(candidate.index);
    if (!current?.path) {
      mergedByIndex.set(candidate.index, candidate);
    }
  });

  return Array.from(mergedByIndex.values()).sort((left, right) => left.index - right.index);
}

function selectedCandidateAfterMerge(
  candidates: Candidate[],
  currentSelection: string | null,
  incomingSelection: string | null = null,
): string | null {
  const availablePaths = new Set(candidates.map((candidate) => candidate.path).filter(Boolean));
  if (currentSelection && availablePaths.has(currentSelection)) return currentSelection;
  if (incomingSelection && availablePaths.has(incomingSelection)) return incomingSelection;
  return candidates.find((candidate) => candidate.path)?.path ?? null;
}

function mergedCandidateState(
  item: Pick<EditableItem, 'candidates' | 'selectedCandidatePath'>,
  incoming: Candidate[],
  incomingSelection: string | null = null,
): Pick<EditableItem, 'candidates' | 'selectedCandidatePath'> {
  const candidates = mergeCandidateSnapshots(item.candidates, incoming);
  return {
    candidates,
    selectedCandidatePath: selectedCandidateAfterMerge(
      candidates,
      item.selectedCandidatePath,
      incomingSelection,
    ),
  };
}

function toEditableItems(items: ImageRequestItem[], refs: ReferenceOption[], narrationById?: Map<string, NarrationManifestItem>): EditableItem[] {
  const byPath = new Map(refs.map((ref) => [ref.path, ref]));
  return items.map((item) => {
    const selectedReferences = item.references.map((ref) => byPath.get(ref) ?? {
      path: ref,
      label: ref.split('/').pop()?.replace(/\.[^.]+$/, '') || ref,
      available: false,
    });
    const narration = narrationById?.get(item.id);
    const sceneKey = inferSceneKey(item.id, narration?.sceneId || item.sceneId);
    const narrationMinDuration = Math.max(1, Math.ceil(narration?.narrationDurationSeconds || 0));
    const configuredVideoDuration = Math.max(
      narration?.configuredVideoDurationSeconds || item.configuredVideoDurationSeconds || 8,
      narrationMinDuration,
    );
    const videoPrompt = narration?.videoPrompt?.trim() || item.videoPrompt?.trim() || defaultVideoPrompt(item);
    const referenceImageMode = item.videoInputMode === 'reference_images';
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
      videoDirtyFields: [],
      videoDraftPrompt: videoPrompt,
      videoQuality: narration?.videoQuality || item.videoQuality || '1080p',
      videoAspectRatio: narration?.videoAspectRatio || item.videoAspectRatio || '16:9',
      videoDurationSec: configuredVideoDuration,
      videoFirstReferencePath: referenceImageMode
        ? null
        : narration?.videoFirstReference || item.videoFirstReference || item.existingImage || selectedReferences[0]?.path || null,
      videoLastReferencePath: narration?.videoLastReference || item.videoLastReference || null,
      videoReferencePaths: narration?.videoReferences?.length
        ? narration.videoReferences
        : item.videoReferences?.length ? item.videoReferences : selectedReferences.map((ref) => ref.path),
      videoTool: narration?.videoTool || item.videoTool || 'kling_3_0',
      sceneKey,
      sceneLabel: sceneLabelFromKey(sceneKey),
      narrationText: narration?.narrationText || '',
      narrationTtsText: narration?.narrationTtsText || narration?.narrationText || '',
      narrationOutput: narration?.narrationOutput || null,
      narrationTool: narration?.narrationTool || 'elevenlabs',
      narrationStatus: narration?.narrationStatus || '',
      narrationReviewStatus: narration?.narrationReviewStatus || '',
      narrationAuthoringStatus: narration?.narrationAuthoringStatus || 'missing',
      narrationRevision: narration?.narrationRevision || 0,
      narrationTextHash: narration?.narrationTextHash || '',
      narrationTtsHash: narration?.narrationTtsHash || '',
      narrationGenerationStatus: narration?.narrationGenerationStatus || 'missing',
      narrationCandidateId: narration?.narrationCandidateId || null,
      narrationCandidateOutput: narration?.narrationCandidateOutput || null,
      narrationCandidateStatus: narration?.narrationCandidateStatus || '',
      narrationCandidateExists: Boolean(narration?.narrationCandidateExists),
      narrationCandidateDurationSec: narration?.narrationCandidateDurationSeconds ?? null,
      narrationGeneratedFromTtsHash: narration?.narrationGeneratedFromTtsHash || '',
      narrationAudioReviewStatus: narration?.narrationAudioReviewStatus || 'pending',
      narrationAudioHumanApproved: Boolean(narration?.narrationAudioHumanApproved),
      narrationDirty: false,
      narrationSaving: false,
      narrationApproving: false,
      narrationSilentOk: Boolean(narration?.narrationSilentOk),
      narrationDurationSec: narration?.narrationDurationSeconds ?? null,
      narrationExists: Boolean(narration?.narrationExists),
      narrationGenerating: false,
      renderVideoPath: narration?.selectedVideoPath || narration?.videoOutput || item.selectedVideoPath || item.videoOutput || null,
      renderVideoExists: Boolean(narration?.videoExists || item.videoExists),
      renderVideoDurationSec: item.videoDurationSeconds || configuredVideoDuration,
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
    const candidateState = mergedCandidateState(previous, item.candidates, item.selectedCandidatePath);
    const preserveNarration = previous.narrationDirty || previous.narrationSaving || previous.narrationApproving || previous.narrationGenerating;
    if (!previous.generating && !previous.promptGenerating && !previous.videoGenerating && !preserveNarration) {
      return { ...item, ...candidateState };
    }
    return {
      ...item,
      generating: previous.generating,
      generationJobStatus: previous.generationJobStatus ?? item.generationJobStatus,
      generationGroupIndex: previous.generationGroupIndex ?? item.generationGroupIndex,
      promptGenerating: previous.promptGenerating,
      ...candidateState,
      videoGenerating: previous.videoGenerating,
      videoCandidates: previous.videoGenerating ? previous.videoCandidates : item.videoCandidates,
      renderVideoPath: previous.renderVideoPath ?? item.renderVideoPath,
      renderVideoExists: previous.renderVideoExists || item.renderVideoExists,
      narrationGenerating: previous.narrationGenerating,
      narrationSaving: previous.narrationSaving,
      narrationApproving: previous.narrationApproving,
      narrationDirty: previous.narrationDirty,
      narrationText: preserveNarration ? previous.narrationText : item.narrationText,
      narrationTtsText: preserveNarration ? previous.narrationTtsText : item.narrationTtsText,
      narrationTool: preserveNarration ? previous.narrationTool : item.narrationTool,
      narrationStatus: preserveNarration ? previous.narrationStatus : item.narrationStatus,
      narrationReviewStatus: preserveNarration ? previous.narrationReviewStatus : item.narrationReviewStatus,
      narrationAuthoringStatus: preserveNarration ? previous.narrationAuthoringStatus : item.narrationAuthoringStatus,
      narrationRevision: preserveNarration ? previous.narrationRevision : item.narrationRevision,
      narrationTextHash: preserveNarration ? previous.narrationTextHash : item.narrationTextHash,
      narrationTtsHash: preserveNarration ? previous.narrationTtsHash : item.narrationTtsHash,
      narrationGenerationStatus: preserveNarration ? previous.narrationGenerationStatus : item.narrationGenerationStatus,
      narrationCandidateId: preserveNarration ? previous.narrationCandidateId : item.narrationCandidateId,
      narrationCandidateOutput: preserveNarration ? previous.narrationCandidateOutput : item.narrationCandidateOutput,
      narrationCandidateStatus: preserveNarration ? previous.narrationCandidateStatus : item.narrationCandidateStatus,
      narrationCandidateExists: preserveNarration ? previous.narrationCandidateExists : item.narrationCandidateExists,
      narrationCandidateDurationSec: preserveNarration ? previous.narrationCandidateDurationSec : item.narrationCandidateDurationSec,
      narrationGeneratedFromTtsHash: preserveNarration ? previous.narrationGeneratedFromTtsHash : item.narrationGeneratedFromTtsHash,
      narrationAudioReviewStatus: preserveNarration ? previous.narrationAudioReviewStatus : item.narrationAudioReviewStatus,
      narrationAudioHumanApproved: preserveNarration ? previous.narrationAudioHumanApproved : item.narrationAudioHumanApproved,
      narrationSilentOk: preserveNarration ? previous.narrationSilentOk : item.narrationSilentOk,
      narrationDurationSec: preserveNarration ? previous.narrationDurationSec : item.narrationDurationSec,
      narrationExists: preserveNarration ? previous.narrationExists : item.narrationExists,
      narrationOutput: preserveNarration ? previous.narrationOutput : item.narrationOutput,
      renderNarrationPath: preserveNarration ? previous.renderNarrationPath : item.renderNarrationPath,
    };
  });
  const nextIds = new Set(next.map((item) => item.id));
  const carryOver = prev.filter(
    (item) => !nextIds.has(item.id) && (item.generating || item.promptGenerating || item.videoGenerating || item.narrationGenerating || item.narrationDirty || item.narrationSaving || item.narrationApproving),
  );
  return carryOver.length ? [...merged, ...carryOver] : merged;
}

function mergeLoadedVideoItemsWithLocalState(prev: EditableItem[], next: EditableItem[]): EditableItem[] {
  const previousById = new Map(prev.map((item) => [item.id, item]));
  const merged = next.map((item) => {
    const previous = previousById.get(item.id);
    if (!previous) return item;
    const candidateState = mergedCandidateState(previous, item.candidates, item.selectedCandidatePath);
    const dirtyFields = new Set(previous.videoDirtyFields);
    const localSelectedVideoPath = previous.renderVideoPath && previous.videoCandidates.some(
      (candidate) => candidate.path === previous.renderVideoPath,
    )
      ? previous.renderVideoPath
      : null;
    return {
      ...item,
      ...candidateState,
      videoCandidates: previous.videoCandidates,
      videoGenerating: previous.videoGenerating,
      videoDirtyFields: previous.videoDirtyFields,
      videoDraftPrompt: dirtyFields.has('videoDraftPrompt') ? previous.videoDraftPrompt : item.videoDraftPrompt,
      videoQuality: dirtyFields.has('videoQuality') ? previous.videoQuality : item.videoQuality,
      videoAspectRatio: dirtyFields.has('videoAspectRatio') ? previous.videoAspectRatio : item.videoAspectRatio,
      videoDurationSec: dirtyFields.has('videoDurationSec') ? previous.videoDurationSec : item.videoDurationSec,
      videoFirstReferencePath: dirtyFields.has('videoFirstReferencePath') ? previous.videoFirstReferencePath : item.videoFirstReferencePath,
      videoLastReferencePath: dirtyFields.has('videoLastReferencePath') ? previous.videoLastReferencePath : item.videoLastReferencePath,
      videoReferencePaths: dirtyFields.has('videoReferencePaths') ? previous.videoReferencePaths : item.videoReferencePaths,
      videoTool: dirtyFields.has('videoTool') ? previous.videoTool : item.videoTool,
      renderVideoPath: localSelectedVideoPath ?? item.renderVideoPath,
      renderVideoExists: localSelectedVideoPath ? previous.renderVideoExists : item.renderVideoExists,
    };
  });
  const nextIds = new Set(next.map((item) => item.id));
  const carryOver = prev.filter((item) => !nextIds.has(item.id) && item.videoGenerating);
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
    if (candidate.error.includes('semantic scene_detail')) return 'scene semantic未完了';
    if (candidate.error.includes('semantic cut_blueprint')) return 'cut semantic未完了';
    if (candidate.error.includes('semantic image_prompt')) return 'prompt semantic未完了';
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

function runtimeStageLabel(runtimeStage?: string | null): string {
  if (!runtimeStage) return '';
  const labels: Record<string, string> = {
    semantic_review_blocked_transport: 'semantic QA が通信 timeout で停止',
    semantic_review_failed_before_media_generation: 'semantic QA 不合格で画像生成前に停止',
    semantic_review_failed_after_media_generation: '画像生成後に semantic QA 不合格',
    app_server_transport_failed: 'Codex app-server 通信失敗',
    create_run_failed: 'ToC作成失敗',
    scene_images_generating: 'シーン画像生成中',
    scene_images_ready_for_review: 'シーン画像レビュー待ち',
  };
  return labels[runtimeStage] || runtimeStage;
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
        {progress.runtimeStage ? `runtime.stage: ${runtimeStageLabel(progress.runtimeStage)}` : 'state.txt / p000_index.md の進捗を表示しています'}
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
        videoDirtyFields: [],
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
        narrationStatus: '',
        narrationReviewStatus: '',
        narrationAuthoringStatus: 'missing',
        narrationRevision: 0,
        narrationTextHash: '',
        narrationTtsHash: '',
        narrationGenerationStatus: 'missing',
        narrationCandidateId: null,
        narrationCandidateOutput: null,
        narrationCandidateStatus: '',
        narrationCandidateExists: false,
        narrationCandidateDurationSec: null,
        narrationGeneratedFromTtsHash: '',
        narrationAudioReviewStatus: 'pending',
        narrationAudioHumanApproved: false,
        narrationDirty: false,
        narrationSaving: false,
        narrationApproving: false,
        narrationSilentOk: false,
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

function itemNarrationDraftReady(item: EditableItem): boolean {
  return Boolean(item.narrationText.trim() || item.narrationTtsText.trim() || item.narrationStatus || item.narrationReviewStatus);
}

function itemNarrationTextLocked(item: EditableItem): boolean {
  return ['human_locked', 'reviewed'].includes(item.narrationAuthoringStatus);
}

function itemNarrationAudioReady(item: EditableItem): boolean {
  if (item.narrationRevision > 0) {
    return (
      item.narrationAudioHumanApproved
      && item.narrationAudioReviewStatus === 'approved'
      && item.narrationGeneratedFromTtsHash === item.narrationTtsHash
      && ((item.narrationExists && item.narrationStatus === 'audio_ready') || (item.narrationTool === 'silent' && item.narrationSilentOk))
    );
  }
  const statusReady = ['audio_ready', 'approved'].includes(item.narrationStatus.trim().toLowerCase()) || item.narrationReviewStatus.trim().toLowerCase() === 'approved';
  return (item.narrationExists && statusReady) || (item.narrationTool === 'silent' && item.narrationSilentOk);
}

function narrationWorkflowPatch(item: NarrationWorkflowItem): Partial<EditableItem> {
  const candidate = item.candidate || null;
  const approvedCandidate = item.approvedCandidate || null;
  const approved = item.audioReview?.status === 'approved' && (
    item.tool === 'silent'
      ? item.generation?.status === 'human_approved'
      : Boolean(item.output) && approvedCandidate?.status === 'human_approved'
  );
  const approvedTtsHash = approvedCandidate?.generated_from_tts_hash || item.generation?.generated_from_tts_hash || '';
  return {
    narrationText: item.text,
    narrationTtsText: item.ttsText,
    narrationTool: item.tool,
    narrationOutput: item.output,
    narrationStatus: item.status,
    narrationAuthoringStatus: item.authoringStatus,
    narrationRevision: item.revision?.number || 0,
    narrationTextHash: item.revision?.text_hash || '',
    narrationTtsHash: item.revision?.tts_hash || '',
    narrationGenerationStatus: item.generation?.status || 'missing',
    narrationCandidateId: candidate?.candidate_id || null,
    narrationCandidateOutput: candidate?.output || null,
    narrationCandidateStatus: candidate?.status || '',
    narrationCandidateExists: Boolean(candidate?.output),
    narrationCandidateDurationSec: candidate?.duration_seconds ?? null,
    narrationGeneratedFromTtsHash: approved ? approvedTtsHash : candidate?.generated_from_tts_hash || '',
    narrationAudioReviewStatus: item.audioReview?.status || 'pending',
    narrationAudioHumanApproved: approved,
    narrationExists: approved && Boolean(item.output),
    narrationDurationSec: approved ? approvedCandidate?.duration_seconds ?? null : null,
    renderNarrationPath: approved ? item.output : null,
    narrationDirty: false,
    narrationSaving: false,
    narrationApproving: false,
  };
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
  videoReady: boolean;
  videoCandidateCount: number;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
  onGenerateVideo: (item: EditableItem) => void;
};

function SceneVideoPanel({ item, runId, references, videoGenerationBusy, videoReady, videoCandidateCount, onPatchItem, onGenerateVideo }: SceneVideoPanelProps) {
  const referenceImageMode = item.videoInputMode === 'reference_images';
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
            disabled={referenceImageMode}
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
          inputProps={{ min: narrationMinDuration, max: MAX_CUT_VIDEO_DURATION_SECONDS }}
          onChange={(event) => {
            const next = Math.max(
              narrationMinDuration,
              Math.min(MAX_CUT_VIDEO_DURATION_SECONDS, Number(event.target.value) || narrationMinDuration),
            );
            onPatchItem(item.id, { videoDurationSec: next });
          }}
        />
      </Box>

      <Box className="videoFrameGrid">
        <Autocomplete
          options={options}
          value={firstReference}
          disabled={referenceImageMode}
          getOptionLabel={(option) => option.label}
          isOptionEqualToValue={(a, b) => a.path === b.path}
          onChange={(_, value) => onPatchItem(item.id, { videoFirstReferencePath: value?.path ?? null })}
          renderOption={(props, option) => (
            <Box component="li" {...props} className="refOption">
              <img src={fileUrl(runId, option.path)} alt="" loading="lazy" decoding="async" />
              <span>{option.label}</span>
            </Box>
          )}
          renderInput={(params) => <TextField {...params} label={referenceImageMode ? 'reference mode（first frameなし）' : 'first reference'} size="small" />}
        />
        <Autocomplete
          options={options}
          value={lastReference}
          disabled={referenceImageMode}
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
              disabled={!videoReady || videoGenerationBusy || item.videoGenerating || !item.videoDraftPrompt.trim()}
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
  const primarySceneImage = useMemo(() => {
    if (viewKind !== 'scene') return null;
    const selectedCandidate = item.selectedCandidatePath
      ? item.candidates.find((candidate) => candidate.path === item.selectedCandidatePath)
      : null;
    if (selectedCandidate?.path) {
      return {
        label: `採用候補 ${selectedCandidate.index}`,
        path: selectedCandidate.path,
        source: 'selected',
      };
    }
    if (item.existingImage) {
      return {
        label: '現在',
        path: item.existingImage,
        source: 'existing',
      };
    }
    const firstCandidate = item.candidates.find((candidate) => candidate.path);
    if (firstCandidate?.path) {
      return {
        label: `候補 ${firstCandidate.index}`,
        path: firstCandidate.path,
        source: 'candidate',
      };
    }
    return null;
  }, [item.candidates, item.existingImage, item.selectedCandidatePath, viewKind]);
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
  const openPrimarySceneImage = useCallback((event?: React.MouseEvent | React.KeyboardEvent) => {
    if (!primarySceneImage) return;
    event?.stopPropagation();
    onSetActiveItemId(item.id);
    onOpenImage({
      itemId: item.id,
      label: primarySceneImage.label,
      path: primarySceneImage.path,
      src: fileUrl(runId, primarySceneImage.path),
    });
  }, [item.id, onOpenImage, onSetActiveItemId, primarySceneImage, runId]);
  const selectedReferenceThumbs = useMemo(
    () =>
      item.selectedReferences.map((ref) => {
        const removeReference = () =>
          onPatchItem(item.id, {
            selectedReferences: item.selectedReferences.filter((selected) => selected.path !== ref.path),
          });
        return (
          <Box key={ref.path} className="referenceThumb">
            {ref.available === false ? (
              <Box className="referencePending" aria-label={`${ref.label}は先行グループで生成待ち`}>
                <Typography variant="caption">生成待ち</Typography>
              </Box>
            ) : (
              <img src={fileUrl(runId, ref.path)} alt={ref.label} loading="lazy" decoding="async" />
            )}
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

          <Button
            className="promptGenerateButton"
            variant="contained"
            startIcon={<AutoAwesomeIcon />}
            disabled={item.generating || item.promptGenerating || !item.draftPrompt.trim()}
            onClick={handleGenerate}
          >
            {item.promptGenerating ? 'プロンプト作成中' : '画像生成'}
          </Button>

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

          </Stack>

          <Box className="comparisonWall">
            <Box className="comparisonHeader">
              <Typography fontWeight={900}>候補比較</Typography>
              <Chip
                size="small"
                label={item.promptGenerating
                  ? 'プロンプト作成中'
                  : item.generating && item.generationJobStatus === 'queued'
                    ? `Group ${item.generationGroupIndex || '-'} / 順番待ち`
                    : item.generating
                      ? `Group ${item.generationGroupIndex || '-'} / 生成中`
                      : item.candidates.length
                        ? '確認待ち'
                        : '未生成'}
              />
            </Box>
            {primarySceneImage && (
              <Box className="scenePrimaryPreview">
                <Box
                  className="scenePrimaryMedia"
                  role="button"
                  tabIndex={0}
                  aria-label={`${item.id}の${primarySceneImage.label}を拡大表示`}
                  onClick={openPrimarySceneImage}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      openPrimarySceneImage(event);
                    }
                  }}
                >
                  <img src={fileUrl(runId, primarySceneImage.path)} alt={`${item.id} ${primarySceneImage.label}`} loading="eager" decoding="async" />
                </Box>
                <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1} className="scenePrimaryCaption">
                  <Typography variant="caption" fontWeight={900} noWrap>{primarySceneImage.label}</Typography>
                  <Chip size="small" color={primarySceneImage.source === 'selected' ? 'primary' : 'default'} label={primarySceneImage.source === 'selected' ? '選択画像' : 'プレビュー'} />
                </Stack>
              </Box>
            )}
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
  videoReady: boolean;
  videoCandidateCount: number;
  onPatchItem: (itemId: string, patch: Partial<EditableItem>) => void;
  onGenerateVideo: (item: EditableItem) => void;
};

const VideoCutCard = React.memo(function VideoCutCard({
  item,
  runId,
  references,
  videoGenerationBusy,
  videoReady,
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
          videoReady={videoReady}
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
  onSaveNarrationText: (item: EditableItem, lock: boolean) => void;
  onGenerateNarration: (item: EditableItem) => void;
  onApproveNarration: (item: EditableItem) => void;
  onConfirmSilentOk: (item: EditableItem) => void;
};

const NarrationCutCard = React.memo(function NarrationCutCard({
  item,
  runId,
  narrationBusy,
  onPatchItem,
  onSaveNarrationText,
  onGenerateNarration,
  onApproveNarration,
  onConfirmSilentOk,
}: NarrationCutCardProps) {
  const handleAudioPlay = useCallback((event: React.SyntheticEvent<HTMLAudioElement>) => {
    document.querySelectorAll('audio').forEach((audio) => {
      if (audio !== event.currentTarget) audio.pause();
    });
  }, []);
  const handleGenerate = useCallback(() => onGenerateNarration(item), [item, onGenerateNarration]);
  const handleSaveDraft = useCallback(() => onSaveNarrationText(item, false), [item, onSaveNarrationText]);
  const handleToggleLock = useCallback(
    () => onSaveNarrationText(item, !itemNarrationTextLocked(item)),
    [item, onSaveNarrationText],
  );
  const handleApprove = useCallback(() => onApproveNarration(item), [item, onApproveNarration]);
  const handleSilentOk = useCallback(() => onConfirmSilentOk(item), [item, onConfirmSilentOk]);
  const audioReady = itemNarrationAudioReady(item);
  const textLocked = itemNarrationTextLocked(item);
  const candidatePreviewReady = Boolean(
    item.narrationCandidateStatus === 'candidate'
    && item.narrationCandidateExists
    && item.narrationCandidateOutput,
  );
  const previewOutput = candidatePreviewReady ? item.narrationCandidateOutput : item.narrationOutput;
  const previewExists = candidatePreviewReady || (item.narrationExists && Boolean(item.narrationOutput));
  const candidateCurrent = Boolean(
    item.narrationCandidateId
    && item.narrationCandidateStatus === 'candidate'
    && item.narrationCandidateExists
    && item.narrationCandidateOutput
    && item.narrationGeneratedFromTtsHash === item.narrationTtsHash,
  );
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
            color={audioReady ? 'success' : 'default'}
            label={item.narrationSilentOk ? '無音OK' : audioReady ? '承認済み' : item.narrationCandidateStatus === 'stale' ? '古い候補' : candidateCurrent ? '候補・未承認' : '未生成'}
          />
        </Stack>

        <Box className="narrationPanel">
          <TextField
            label="ナレーション文面"
            multiline
            minRows={5}
            value={item.narrationText}
            disabled={textLocked}
            onChange={(event) => onPatchItem(item.id, { narrationText: event.target.value, narrationDirty: true, narrationAudioHumanApproved: false })}
          />
          <TextField
            label="TTS文面"
            multiline
            minRows={3}
            value={item.narrationTtsText}
            disabled={textLocked}
            onChange={(event) => onPatchItem(item.id, { narrationTtsText: event.target.value, narrationDirty: true, narrationAudioHumanApproved: false })}
          />
          <Box className="narrationSettingsGrid">
            <FormControl size="small">
              <InputLabel>tool</InputLabel>
              <Select
                label="tool"
                value={item.narrationTool}
                disabled={textLocked}
                onChange={(event) => onPatchItem(item.id, { narrationTool: event.target.value, narrationDirty: true, narrationAudioHumanApproved: false })}
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
              disabled
              helperText="承認済み音声のみ。候補はrevision別pathへ保存されます。"
            />
          </Box>
          <Box className="audioReviewBox">
            {previewExists && previewOutput ? (
              <audio src={audioFileUrl(runId, previewOutput)} controls preload="metadata" onPlay={handleAudioPlay} />
            ) : (
              <Typography variant="caption" color="text.secondary">音声ファイル未生成</Typography>
            )}
            <Button variant="outlined" onClick={handleSaveDraft} disabled={narrationBusy || item.narrationSaving || textLocked || !item.narrationDirty}>
              下書き保存
            </Button>
            <Button variant={textLocked ? 'outlined' : 'contained'} onClick={handleToggleLock} disabled={narrationBusy || item.narrationSaving || (!textLocked && !item.narrationText.trim() && !item.narrationTtsText.trim())}>
              {textLocked ? '確定解除' : '文面を確定'}
            </Button>
            <Button
              variant="outlined"
              startIcon={<RecordVoiceOverIcon />}
              onClick={handleGenerate}
              disabled={narrationBusy || item.narrationGenerating || (item.narrationTool !== 'silent' && !item.narrationText.trim() && !item.narrationTtsText.trim())}
            >
              音声候補を生成
            </Button>
            {item.narrationTool !== 'silent' && (
              <Button color="success" variant="contained" onClick={handleApprove} disabled={narrationBusy || item.narrationApproving || !textLocked || !candidateCurrent}>
                この候補を承認
              </Button>
            )}
            {item.narrationTool === 'silent' && (
              <Button
                variant={item.narrationSilentOk ? 'contained' : 'outlined'}
                color={item.narrationSilentOk ? 'success' : 'primary'}
                onClick={handleSilentOk}
                disabled={narrationBusy || item.narrationGenerating}
              >
                このcutは無音OK
              </Button>
            )}
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
  const narrationExceedsVideoDurationLimit = minVideoDuration > MAX_CUT_VIDEO_DURATION_SECONDS;
  const configuredVideoExceedsDurationLimit = item.renderVideoDurationSec > MAX_CUT_VIDEO_DURATION_SECONDS;
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
              inputProps={{ min: Math.min(minVideoDuration, MAX_CUT_VIDEO_DURATION_SECONDS), max: MAX_CUT_VIDEO_DURATION_SECONDS }}
              onChange={(event) => {
                const boundedMinimum = Math.min(minVideoDuration, MAX_CUT_VIDEO_DURATION_SECONDS);
                const next = Math.max(
                  boundedMinimum,
                  Math.min(MAX_CUT_VIDEO_DURATION_SECONDS, Number(event.target.value) || boundedMinimum),
                );
                onPatchItem(item.id, { renderVideoDurationSec: next, videoDurationSec: next });
              }}
            />
            <TextField
              size="small"
              label="話し出し秒"
              type="number"
              value={item.renderNarrationOffsetSec}
              inputProps={{ min: 0, max: MAX_CUT_VIDEO_DURATION_SECONDS, step: 0.1 }}
              onChange={(event) => {
                const next = Math.max(0, Math.min(MAX_CUT_VIDEO_DURATION_SECONDS, Number(event.target.value) || 0));
                const nextMin = Math.max(1, Math.ceil(narrationDuration + next));
                onPatchItem(item.id, {
                  renderNarrationOffsetSec: next,
                  renderVideoDurationSec: Math.min(MAX_CUT_VIDEO_DURATION_SECONDS, Math.max(item.renderVideoDurationSec, nextMin)),
                  videoDurationSec: Math.min(MAX_CUT_VIDEO_DURATION_SECONDS, Math.max(item.videoDurationSec, nextMin)),
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
          {narrationExceedsVideoDurationLimit ? (
            <Chip size="small" color="error" label={`音声+offset ${minVideoDuration}s。60秒以内のcutへ分割してください`} />
          ) : configuredVideoExceedsDurationLimit ? (
            <Chip size="small" color="error" label="動画秒数を60秒以内にしてください" />
          ) : isShort ? (
            <Chip size="small" color="warning" label={`最低 ${minVideoDuration}s`} />
          ) : null}
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
  const [candidateCount, setCandidateCount] = useState(1);
  const [candidateCountDraft, setCandidateCountDraft] = useState(1);
  const [videoCandidateCount, setVideoCandidateCount] = useState(3);
  const [videoCandidateCountDraft, setVideoCandidateCountDraft] = useState(3);
  const [activeImageSceneKey, setActiveImageSceneKey] = useState('');
  const [activeImageCutId, setActiveImageCutId] = useState('');
  const [activeVideoSceneKey, setActiveVideoSceneKey] = useState('');
  const [items, setItems] = useState<EditableItem[]>([]);
  const [videoTargetItems, setVideoTargetItems] = useState<EditableItem[]>([]);
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
  const [bulkJobId, setBulkJobId] = useState<string | null>(null);
  const [bulkGenerating, setBulkGenerating] = useState(false);
  const [bulkTotal, setBulkTotal] = useState(0);
  const [bulkCompletedCount, setBulkCompletedCount] = useState(0);
  const [bulkFailedCount, setBulkFailedCount] = useState(0);
  const [videoBulkTotal, setVideoBulkTotal] = useState(0);
  const [videoBulkCompletedCount, setVideoBulkCompletedCount] = useState(0);
  const [videoBulkFailedCount, setVideoBulkFailedCount] = useState(0);
  const [narrationBusy, setNarrationBusy] = useState(false);
  const [narrationDraftBusy, setNarrationDraftBusy] = useState(false);
  const [narrationStatus, setNarrationStatus] = useState<string | null>(null);
  const [narrationBulkTotal, setNarrationBulkTotal] = useState(0);
  const [narrationBulkCompletedCount, setNarrationBulkCompletedCount] = useState(0);
  const [narrationBulkFailedCount, setNarrationBulkFailedCount] = useState(0);
  const [narrationAudioSetHash, setNarrationAudioSetHash] = useState('');
  const [narrationMutationPendingCount, setNarrationMutationPendingCount] = useState(0);
  const [narrationReviewBusy, setNarrationReviewBusy] = useState(false);
  const [narrationReviewFindings, setNarrationReviewFindings] = useState<string[]>([]);
  const [narrationReviewReport, setNarrationReviewReport] = useState('');
  const [fullNarrationListening, setFullNarrationListening] = useState(false);
  const [fullNarrationListeningItem, setFullNarrationListeningItem] = useState('');
  const [fullNarrationListenEvidence, setFullNarrationListenEvidence] = useState<NarrationListenEvidence | null>(null);
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
  const [createRunMode, setCreateRunMode] = useState<CreateRunMode>('normal');
  const [createRunTargetDurationSeconds, setCreateRunTargetDurationSeconds] = useState('300');
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
  const [confirmNarrationReplaceOpen, setConfirmNarrationReplaceOpen] = useState(false);
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
  const chatToggleButtonRef = useRef<HTMLButtonElement | null>(null);
  const chatInputRef = useRef<HTMLInputElement | null>(null);
  const runIdRef = useRef(runId);
  const requestKindRef = useRef<ViewKind>('asset');
  const itemsScopeRef = useRef('');
  const loadRunRequestsEpochRef = useRef(0);
  const narrationMutationEpochRef = useRef(0);
  const narrationMutationQueueRef = useRef<Promise<void>>(Promise.resolve());
  const fullNarrationPlaybackTokenRef = useRef(0);
  const cancelCurrentFullNarrationAudioRef = useRef<(() => void) | null>(null);
  const selectedRun = useMemo(() => runs.find((run) => run.id === runId), [runId, runs]);
  const requestKind = workspaceMode === 'image' ? viewKind : 'scene';
  runIdRef.current = runId;
  requestKindRef.current = requestKind;
  const visibleItems = useMemo(() => {
    if (workspaceMode !== 'image') return items.filter(isSceneCutItem);
    if (viewKind === 'scene') return items.filter(isSceneCutItem);
    const existingItemsByOutput = new Map(items.map((item) => [item.output, item]));
    const fallbackItems = existingAssetItems(references).filter((item) => !existingItemsByOutput.has(item.output));
    return sortAssetItems([...items, ...fallbackItems].filter((item) => itemMatchesAssetFilter(item, assetFilter)));
  }, [assetFilter, items, references, viewKind, workspaceMode]);
  const videoSceneGroups = useMemo(() => {
    const groups = new Map<string, { key: string; label: string; items: EditableItem[] }>();
    const sourceItems = workspaceMode === 'video' ? videoTargetItems : visibleItems;
    for (const item of sourceItems) {
      const key = item.sceneKey || 'scene';
      const existing = groups.get(key);
      if (existing) {
        existing.items.push(item);
      } else {
        groups.set(key, { key, label: item.sceneLabel || sceneLabelFromKey(key), items: [item] });
      }
    }
    return Array.from(groups.values());
  }, [videoTargetItems, visibleItems, workspaceMode]);
  const imageSceneGroups = useMemo(() => {
    if (workspaceMode !== 'image' || viewKind !== 'scene') return [];
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
  }, [viewKind, visibleItems, workspaceMode]);
  const activeImageScene = useMemo(
    () => imageSceneGroups.find((group) => group.key === activeImageSceneKey) ?? imageSceneGroups[0] ?? null,
    [activeImageSceneKey, imageSceneGroups],
  );
  const activeVideoScene = useMemo(
    () => videoSceneGroups.find((group) => group.key === activeVideoSceneKey) ?? videoSceneGroups[0] ?? null,
    [activeVideoSceneKey, videoSceneGroups],
  );
  const imageSceneItems = workspaceMode === 'image' && viewKind === 'scene' ? activeImageScene?.items ?? [] : [];
  const activeImageCutIndex = useMemo(() => {
    if (!imageSceneItems.length) return -1;
    const index = imageSceneItems.findIndex((item) => item.id === activeImageCutId);
    return index >= 0 ? index : 0;
  }, [activeImageCutId, imageSceneItems]);
  const activeImageCutItem = activeImageCutIndex >= 0 ? imageSceneItems[activeImageCutIndex] : null;
  const imageDisplayItems = workspaceMode === 'image' && viewKind === 'scene'
    ? activeImageCutItem ? [activeImageCutItem] : []
    : visibleItems;
  const imageBulkItems = workspaceMode === 'image' && viewKind === 'scene'
    ? imageSceneItems
    : visibleItems.filter((item) => item.executionLane !== 'existing_asset');
  const videoDisplayItems = workspaceMode === 'video' ? activeVideoScene?.items ?? [] : visibleItems;
  const displayedItemCount = workspaceMode === 'image' ? imageDisplayItems.length : workspaceMode === 'video' ? videoDisplayItems.length : visibleItems.length;
  const sceneCutItems = useMemo(() => items.filter(isSceneCutItem), [items]);
  const narrationApprovalTimeline = useMemo<NarrationTimelinePayload[]>(() => sceneCutItems.map((item) => ({
    item_id: item.id,
    video_duration_seconds: Math.max(
      item.renderVideoDurationSec,
      Math.ceil((item.narrationDurationSec || 0) + item.renderNarrationOffsetSec),
      1,
    ),
    narration_offset_seconds: item.renderNarrationOffsetSec,
  })), [sceneCutItems]);
  const narrationApprovalTimelineSignature = useMemo(
    () => JSON.stringify(narrationApprovalTimeline),
    [narrationApprovalTimeline],
  );
  const narrationDurationLimitViolation = useMemo(
    () => narrationApprovalTimeline.find((item) => item.video_duration_seconds > MAX_CUT_VIDEO_DURATION_SECONDS) || null,
    [narrationApprovalTimeline],
  );
  const narrationDraftReadyCount = useMemo(() => sceneCutItems.filter(itemNarrationDraftReady).length, [sceneCutItems]);
  const narrationAudioReadyCount = useMemo(() => sceneCutItems.filter(itemNarrationAudioReady).length, [sceneCutItems]);
  const hasNarrationDrafts = sceneCutItems.length > 0 && narrationDraftReadyCount > 0;
  const allNarrationAudioReady = sceneCutItems.length > 0 && narrationAudioReadyCount === sceneCutItems.length;
  const allNarrationTextReady = sceneCutItems.length > 0 && sceneCutItems.every((item) => (
    !item.narrationDirty
    && (
      item.narrationAuthoringStatus === 'silent'
      || (itemNarrationTextLocked(item) && Boolean(item.narrationText.trim() || item.narrationTtsText.trim()))
    )
  ));
  const narrationTextReviewPassed = Boolean(runProgress?.slots.some((slot) => slot.code === 'p720' && slot.state === 'done'));
  const narrationRunApproved = Boolean(runProgress?.slots.some((slot) => slot.code === 'p750' && slot.state === 'done'));
  const fullNarrationListenIsCurrent = Boolean(
    fullNarrationListenEvidence
    && fullNarrationListenEvidence.audio_set_hash === narrationAudioSetHash
    && JSON.stringify(fullNarrationListenEvidence.timeline) === narrationApprovalTimelineSignature
    && JSON.stringify(fullNarrationListenEvidence.item_ids) === JSON.stringify(sceneCutItems.map((item) => item.id)),
  );
  const narrationReadyForVideo = allNarrationAudioReady && narrationRunApproved;
  const cancelFullNarrationPlayback = useCallback(() => {
    fullNarrationPlaybackTokenRef.current += 1;
    cancelCurrentFullNarrationAudioRef.current?.();
    cancelCurrentFullNarrationAudioRef.current = null;
    setFullNarrationListening(false);
    setFullNarrationListeningItem('');
  }, []);
  const canGoPrevImageCut = activeImageCutIndex > 0;
  const canGoNextImageCut = activeImageCutIndex >= 0 && activeImageCutIndex < imageSceneItems.length - 1;
  const moveImageCut = useCallback((delta: -1 | 1) => {
    if (!imageSceneItems.length || activeImageCutIndex < 0) return;
    const nextIndex = Math.min(Math.max(activeImageCutIndex + delta, 0), imageSceneItems.length - 1);
    const nextItem = imageSceneItems[nextIndex];
    if (!nextItem) return;
    setActiveImageCutId(nextItem.id);
    setActiveItemId(nextItem.id);
  }, [activeImageCutIndex, imageSceneItems]);
  const imageGenerationActive = bulkGenerating || regenerateBusy || addAssetBusy || items.some((item) => item.generating || item.promptGenerating);
  const narrationMutationActive = narrationMutationPendingCount > 0;
  const narrationGenerationActive = narrationBusy
    || narrationDraftBusy
    || narrationReviewBusy
    || narrationMutationActive
    || fullNarrationListening
    || items.some((item) => item.narrationGenerating || item.narrationSaving || item.narrationApproving);
  const videoGenerationActive = videoPromptBusy
    || items.some((item) => item.videoGenerating)
    || videoTargetItems.some((item) => item.videoGenerating);
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

  const ensureVideoItemsInState = useCallback((targetItems: EditableItem[]) => {
    if (!targetItems.length) return;
    setVideoTargetItems((prev) => {
      const existingIds = new Set(prev.map((item) => item.id));
      const additions = targetItems.filter((item) => !existingIds.has(item.id));
      return additions.length ? [...prev, ...additions] : prev;
    });
  }, []);

  const runNarrationMutation = useCallback(<T,>(targetRunId: string, operation: () => Promise<T>): Promise<T> => {
    setNarrationMutationPendingCount((count) => count + 1);
    const queued = narrationMutationQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        if (runIdRef.current !== targetRunId) {
          throw new Error('selected run changed before narration mutation started');
        }
        narrationMutationEpochRef.current += 1;
        return operation();
      });
    narrationMutationQueueRef.current = queued.then(
      () => undefined,
      () => undefined,
    );
    return queued.finally(() => {
      setNarrationMutationPendingCount((count) => Math.max(0, count - 1));
    });
  }, []);

  const loadRuns = useCallback(async (preferredRunId?: string) => {
    const data = await jsonFetch<{ runs: RunFolder[] }>('/api/image-gen/runs');
    setRuns(data.runs);
    setRunId((current) => preferredRunId || current || data.runs[0]?.id || '');
    return data.runs;
  }, []);

  const loadRunRequests = useCallback(async (targetRunId: string, targetKind: ViewKind) => {
    const targetScopeKey = imageRequestScopeKey(targetRunId, targetKind);
    const requestEpoch = loadRunRequestsEpochRef.current + 1;
    loadRunRequestsEpochRef.current = requestEpoch;
    const narrationMutationEpoch = narrationMutationEpochRef.current;
    const requestIsCurrent = () => (
      loadRunRequestsEpochRef.current === requestEpoch
      && narrationMutationEpochRef.current === narrationMutationEpoch
      && runIdRef.current === targetRunId
      && requestKindRef.current === targetKind
    );
    setBusy(true);
    try {
      const data = await jsonFetch<{ items: ImageRequestItem[]; references: ReferenceOption[]; progress: RunProgress }>(
        `/api/image-gen/requests?run_id=${encodeURIComponent(targetRunId)}&kind=${targetKind}`,
      );
      let narrationById: Map<string, NarrationManifestItem> | undefined;
      let audioSetHash = '';
      let progress = data.progress;
      if (targetKind === 'scene') {
        try {
          const narrationData = await jsonFetch<{ items: NarrationManifestItem[]; audioSetHash: string; progress: RunProgress }>(
            `/api/image-gen/narration-items?run_id=${encodeURIComponent(targetRunId)}`,
          );
          narrationById = new Map(narrationData.items.map((item) => [item.itemId, item]));
          audioSetHash = narrationData.audioSetHash || '';
          progress = narrationData.progress || progress;
        } catch (error) {
          console.error(error);
        }
      }
      if (!requestIsCurrent()) return;
      const loadedItems = toEditableItems(data.items, data.references, narrationById);
      const sameScope = itemsScopeRef.current === targetScopeKey;
      itemsScopeRef.current = targetScopeKey;
      setReferences(data.references);
      setItems((prev) => sameScope ? mergeLoadedItemsWithInflight(prev, loadedItems) : loadedItems);
      setRunProgress(progress);
      if (targetKind === 'scene') setNarrationAudioSetHash(audioSetHash);
    } catch (error) {
      console.error(error);
      if (!requestIsCurrent()) return;
      itemsScopeRef.current = targetScopeKey;
      setItems([]);
      setReferences([]);
      setRunProgress(null);
      if (targetKind === 'scene') setNarrationAudioSetHash('');
    } finally {
      if (requestIsCurrent()) setBusy(false);
    }
  }, []);

  const loadVideoTargets = useCallback(async (targetRunId: string) => {
    const data = await jsonFetch<{
      items: ImageRequestItem[];
      references: ReferenceOption[];
      progress: RunProgress;
    }>(`/api/image-gen/video-items?run_id=${encodeURIComponent(targetRunId)}`);
    if (runIdRef.current !== targetRunId) return [];
    const loadedItems = toEditableItems(data.items, data.references);
    setVideoTargetItems((prev) => mergeLoadedVideoItemsWithLocalState(prev, loadedItems));
    setReferences(data.references);
    setRunProgress(data.progress);
    return loadedItems;
  }, []);

  useEffect(() => {
    loadRuns()
      .catch((error) => console.error(error));
  }, [loadRuns]);

  useEffect(() => {
    const nextScopeKey = imageRequestScopeKey(runId, requestKind);
    if (itemsScopeRef.current === nextScopeKey) return;
    itemsScopeRef.current = nextScopeKey;
    setItems([]);
    setReferences([]);
  }, [requestKind, runId]);

  useEffect(() => {
    setNarrationAudioSetHash('');
    setNarrationReviewFindings([]);
    setNarrationReviewReport('');
    setVideoTargetItems([]);
  }, [runId]);

  useEffect(() => {
    cancelFullNarrationPlayback();
    setFullNarrationListenEvidence(null);
  }, [cancelFullNarrationPlayback, narrationApprovalTimelineSignature, narrationAudioSetHash, runId]);

  useEffect(() => {
    if (!runId) return;
    void loadRunRequests(runId, requestKind);
  }, [loadRunRequests, requestKind, runId]);

  useEffect(() => {
    if (!runId || workspaceMode !== 'video' || videoPromptBusy) return;
    void loadVideoTargets(runId).catch((error) => console.error(error));
  }, [loadVideoTargets, runId, videoPromptBusy, workspaceMode]);

  const refreshCurrentRun = useCallback(async () => {
    if (!runId || busy) return;
    try {
      await loadRuns(runId);
      await loadRunRequests(runId, requestKind);
    } catch (error) {
      console.error(error);
    }
  }, [busy, loadRunRequests, loadRuns, requestKind, runId]);

  useEffect(() => {
    if (!runId || !generationInFlight) return;
    let cancelled = false;
    let pollRequestEpoch = 0;
    const pollProgress = async () => {
      const requestEpoch = pollRequestEpoch + 1;
      pollRequestEpoch = requestEpoch;
      const narrationMutationEpoch = narrationMutationEpochRef.current;
      try {
        const data = await jsonFetch<ProgressResponse>(`/api/image-gen/progress?run_id=${encodeURIComponent(runId)}`);
        if (
          !cancelled
          && requestEpoch === pollRequestEpoch
          && narrationMutationEpoch === narrationMutationEpochRef.current
          && runIdRef.current === runId
        ) {
          setRunProgress(data.progress);
        }
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
    if (workspaceMode !== 'image' || viewKind !== 'scene') return;
    setActiveImageSceneKey((current) => {
      if (current && imageSceneGroups.some((group) => group.key === current)) return current;
      return imageSceneGroups[0]?.key || '';
    });
  }, [imageSceneGroups, viewKind, workspaceMode]);

  useEffect(() => {
    if (workspaceMode !== 'image' || viewKind !== 'scene') return;
    setActiveImageCutId((current) => {
      if (current && imageSceneItems.some((item) => item.id === current)) return current;
      return imageSceneItems[0]?.id || '';
    });
  }, [imageSceneItems, viewKind, workspaceMode]);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1100px)');
    const update = () => setIsNarrowViewport(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!chatOpen) return;
    window.setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [chatOpen]);

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

  const patchVideoItem = useCallback((itemId: string, patch: Partial<EditableItem>) => {
    setVideoTargetItems((prev) => prev.map((item) => (
      item.id === itemId ? { ...item, ...patch } : item
    )));
  }, []);

  const patchVideoDraftItem = useCallback((itemId: string, patch: Partial<EditableItem>) => {
    const changedFields = Object.keys(patch).filter((field): field is VideoDraftField => VIDEO_DRAFT_FIELD_SET.has(field));
    setVideoTargetItems((prev) => prev.map((item) => {
      if (item.id !== itemId) return item;
      const dirtyFields = new Set(item.videoDirtyFields);
      changedFields.forEach((field) => dirtyFields.add(field));
      return { ...item, ...patch, videoDirtyFields: Array.from(dirtyFields) };
    }));
  }, []);

  const applyBulkGenerationJob = useCallback((
    job: BulkGenerationJob,
    options: { preserveLoadedCandidates?: boolean } = {},
  ) => {
    if (runIdRef.current !== job.runId || requestKindRef.current !== job.kind) return;
    const active = job.status === 'queued' || job.status === 'running';
    setBulkGenerating(active);
    setBulkTotal(job.totalCount);
    setBulkCompletedCount(job.completedCount);
    setBulkFailedCount(job.failedCount);
    const resultById = new Map(job.results.map((result) => [result.itemId, result]));
    setItems((prev) => prev.map((item) => {
      const result = resultById.get(item.id);
      if (!result) return item;
      if (options.preserveLoadedCandidates) {
        const candidateState = mergedCandidateState(item, result.candidates || []);
        return {
          ...item,
          ...candidateState,
          generating: false,
          generationJobStatus: result.status,
          generationGroupIndex: result.groupIndex,
        };
      }
      const incomingCandidates = result.candidates?.length
        ? result.candidates
        : [{ index: 1, status: result.status, path: null, error: result.error }];
      return {
        ...item,
        generating: result.status === 'queued' || result.status === 'running',
        generationJobStatus: result.status,
        generationGroupIndex: result.groupIndex,
        ...mergedCandidateState(item, incomingCandidates),
      };
    }));
  }, []);

  const closeChat = useCallback(() => {
    setChatOpen(false);
    window.setTimeout(() => chatToggleButtonRef.current?.focus(), 0);
  }, []);

  const setActiveItemIdStable = useCallback((itemId: string) => setActiveItemId(itemId), []);
  const openEnlargedImage = useCallback((image: EnlargedImage) => setEnlargedImage(image), []);
  const closeEnlargedImage = useCallback(() => setEnlargedImage(null), []);

  const fetchCandidates = useCallback(
    (itemId: string) =>
      jsonFetch<CandidatesResponse>(
        `/api/image-gen/candidates?run_id=${encodeURIComponent(runId)}&item_id=${encodeURIComponent(itemId)}&kind=${viewKind}`,
      ),
    [runId, viewKind],
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
          prompt_policy_version: item.promptPolicyVersion || null,
          debug_prompt_source: item.debugPromptSource || {},
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
    const generationRunId = runId;
    const generationKind = viewKind;
    const generationScopeKey = imageRequestScopeKey(generationRunId, generationKind);
    const generationIsCurrent = () => (
      runIdRef.current === generationRunId
      && requestKindRef.current === generationKind
      && itemsScopeRef.current === generationScopeKey
    );
    ensureItemsInState([item]);
    setActiveItemId(item.id);
    setInsertStatus('idle');
    setItems((prev) => prev.map((current) => (
      current.id === item.id
        ? { ...current, ...mergedCandidateState(current, []), generating: true }
        : current
    )));
    try {
      const data = await generateWithRecovery(item);
      if (!generationIsCurrent()) return;
      setItems((prev) => prev.map((current) => (
        current.id === item.id
          ? { ...current, ...mergedCandidateState(current, data.candidates) }
          : current
      )));
    } catch (error) {
      console.error(error);
      if (!generationIsCurrent()) return;
      const failedCandidate: Candidate = { index: 1, status: 'failed', path: null, error: candidateErrorMessage(error) };
      setItems((prev) => prev.map((current) => (
        current.id === item.id
          ? { ...current, ...mergedCandidateState(current, [failedCandidate]) }
          : current
      )));
    } finally {
      if (generationIsCurrent()) patchItem(item.id, { generating: false });
    }
  }, [ensureItemsInState, generateWithRecovery, patchItem, runId, viewKind]);

  const generateItems = useCallback(async (targetItems: EditableItem[]) => {
    if (!runId) return;
    const generationRunId = runId;
    const generationKind = viewKind;
    const generationScopeKey = imageRequestScopeKey(generationRunId, generationKind);
    const generationIsCurrent = () => (
      runIdRef.current === generationRunId
      && requestKindRef.current === generationKind
      && itemsScopeRef.current === generationScopeKey
    );
    ensureItemsInState(targetItems);
    const targetIds = new Set(targetItems.map((item) => item.id));
    setBulkGenerating(true);
    setBulkTotal(targetIds.size);
    setBulkCompletedCount(0);
    setBulkFailedCount(0);
    setInsertStatus('idle');
    setActiveItemId(targetItems[0]?.id ?? null);
    setItems((prev) => prev.map((item) => (
      targetIds.has(item.id)
        ? { ...item, ...mergedCandidateState(item, []), generating: true }
        : item
    )));

    try {
      const requestItems = targetItems.map((item) => ({
        run_id: runId,
        kind: viewKind,
        item_id: item.id,
        prompt: item.draftPrompt,
        prompt_policy_version: item.promptPolicyVersion || null,
        debug_prompt_source: item.debugPromptSource || {},
        references: item.selectedReferences.map((ref) => ref.path),
        candidate_count: candidateCount,
      }));
      const job = await jsonFetch<BulkGenerationJob>('/api/image-gen/generate-bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          kind: viewKind,
          items: requestItems,
          background: true,
        }),
      });
      applyBulkGenerationJob(job);
      if (job.status === 'queued' || job.status === 'running') {
        setBulkJobId(job.jobId);
      }
    } catch (error) {
      const message = candidateErrorMessage(error);
      if (!generationIsCurrent()) return;
      setBulkGenerating(false);
      setBulkCompletedCount(0);
      setBulkFailedCount(targetIds.size);
      setItems((prev) =>
        prev.map((prevItem) =>
          targetIds.has(prevItem.id)
              ? {
                  ...prevItem,
                  generating: false,
                  ...mergedCandidateState(prevItem, [{ index: 1, status: 'failed', path: null, error: message }]),
                }
            : prevItem,
        ),
      );
    }
  }, [applyBulkGenerationJob, candidateCount, ensureItemsInState, runId, viewKind]);

  useEffect(() => {
    if (!bulkJobId) return;
    let cancelled = false;
    let timer: number | null = null;
    const poll = async () => {
      try {
        const job = await jsonFetch<BulkGenerationJob>(
          `/api/image-gen/generate-bulk/${encodeURIComponent(bulkJobId)}`,
        );
        if (cancelled || runIdRef.current !== job.runId) return;
        if (job.status === 'queued' || job.status === 'running') {
          applyBulkGenerationJob(job);
          timer = window.setTimeout(() => void poll(), 2000);
          return;
        }
        setBulkJobId(null);
        await loadRunRequests(job.runId, job.kind);
        if (cancelled || runIdRef.current !== job.runId) return;
        applyBulkGenerationJob(job);
      } catch (error) {
        if (cancelled) return;
        console.error(error);
        timer = window.setTimeout(() => void poll(), 3000);
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [applyBulkGenerationJob, bulkJobId, loadRunRequests]);

  useEffect(() => {
    setBulkJobId(null);
    setBulkGenerating(false);
    setBulkTotal(0);
    setBulkCompletedCount(0);
    setBulkFailedCount(0);
    if (!runId) return;
    const controller = new AbortController();
    const reconnect = async () => {
      try {
        const response = await fetch(
          `/api/image-gen/runs/${encodeURIComponent(runId)}/generate-bulk/active?kind=${viewKind}`,
          { signal: controller.signal },
        );
        if (response.status === 404) return;
        if (!response.ok) throw new Error((await response.text()) || response.statusText);
        const job = await response.json() as BulkGenerationJob;
        if (controller.signal.aborted || runIdRef.current !== job.runId) return;
        if (job.status === 'queued' || job.status === 'running') {
          applyBulkGenerationJob(job);
          setBulkJobId(job.jobId);
          return;
        }
        await loadRunRequests(job.runId, job.kind);
        if (controller.signal.aborted || runIdRef.current !== job.runId) return;
        applyBulkGenerationJob(job, { preserveLoadedCandidates: true });
      } catch (error) {
        if (!controller.signal.aborted) console.error(error);
      }
    };
    void reconnect();
    return () => controller.abort();
  }, [applyBulkGenerationJob, loadRunRequests, runId, viewKind]);

  const generateBulk = async () => {
    await generateItems([...imageBulkItems]);
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
    const hasCompiledV2 = targetItems.some((item) => item.promptPolicyVersion === 'image_api_prompt_v2');
    setRegenerateStatus(
      hasCompiledV2
        ? `${settingsTargetLabel(settingsTarget)}の設計を更新して再コンパイル中`
        : `${settingsTargetLabel(settingsTarget)}のプロンプトを生成中`,
    );
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
      const updatedIds = new Set(data.updated);
      const requestKind = nextView.viewKind;
      const requestData = await jsonFetch<{ items: ImageRequestItem[]; references: ReferenceOption[] }>(
        `/api/image-gen/requests?run_id=${encodeURIComponent(runId)}&kind=${requestKind}`,
      );
      if (runIdRef.current !== runId || requestKindRef.current !== requestKind) return;
      setReferences(requestData.references);
      const loadedItems = toEditableItems(requestData.items, requestData.references);
      const targetScopeKey = imageRequestScopeKey(runId, requestKind);
      const sameScope = itemsScopeRef.current === targetScopeKey;
      itemsScopeRef.current = targetScopeKey;
      const nextGenerated = loadedItems
        .filter((item) => updatedIds.has(item.id))
        .map((item) => ({ ...item, generating: false }));
      setItems((prev) => (sameScope ? mergeLoadedItemsWithInflight(prev, loadedItems) : loadedItems).map((item) => (
        updatedIds.has(item.id) ? { ...item, generating: false } : item
      )));
      setRegeneratedItems(nextGenerated);
      setRegenerateStatus(
        data.operation === 'recompiled'
          ? `${data.updated.length}件の設計を更新して再コンパイルしました`
          : `${data.updated.length}件のプロンプトを更新しました`,
      );
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
    video_duration_seconds: Math.max(item.videoDurationSec, Math.ceil(item.narrationDurationSec || 0), 1),
    video_first_reference: item.videoInputMode === 'reference_images' ? '' : item.videoFirstReferencePath || item.selectedCandidatePath || item.existingImage || item.output,
    video_last_reference: item.videoLastReferencePath ?? '',
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
    const reviewItems = workspaceMode === 'video' ? videoTargetItems : visibleItems;
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
          items: buildReviewItems(reviewItems),
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
  }, [buildReviewItems, runId, videoTargetItems, viewKind, visibleItems, workspaceMode]);

  const materializeVideoPrompts = useCallback(async (targetItems: EditableItem[]) => {
    if (!runId || !targetItems.length) return;
    await jsonFetch<{ status: string }>('/api/image-gen/video-prompts/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        run_id: runId,
        note: 'frontend video generation materialization',
        items: buildReviewItems(targetItems),
        replace_all: false,
        approve_for_generation: true,
      }),
    });
  }, [buildReviewItems, runId]);

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
    if (!narrationReadyForVideo) {
      applyWorkspaceMode('video');
      setVideoPromptStatus('動画生成には全cut音声の個別承認と全編音声承認が必要です');
      return;
    }
    setVideoPromptStatus(null);
    applyWorkspaceMode('video');
    await loadVideoTargets(runId);
    setConfirmVideoPromptOpen(true);
  }, [applyWorkspaceMode, loadVideoTargets, narrationReadyForVideo, runId]);

  const buildVideoGenerateItem = useCallback((item: EditableItem, count = videoCandidateCount): VideoGenerateItemPayload => ({
    item_id: item.id,
    prompt: item.videoDraftPrompt,
    first_reference: item.videoInputMode === 'reference_images' ? '' : item.videoFirstReferencePath || item.selectedCandidatePath || item.existingImage || item.output,
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
    if (!narrationReadyForVideo) {
      setVideoPromptStatus('動画生成には全編音声承認が必要です');
      return;
    }
    ensureVideoItemsInState([item]);
    setActiveItemId(item.id);
    setVideoPromptBusy(true);
    setVideoPromptStatus(`動画生成中 ${item.id}`);
    setVideoBulkTotal(1);
    setVideoBulkCompletedCount(0);
    setVideoBulkFailedCount(0);
    patchVideoItem(item.id, { videoGenerating: true, videoCandidates: [] });
    try {
      await materializeVideoPrompts([item]);
      const data = await generateVideoRequest(item);
      const firstVideoPath = data.candidates.find((candidate) => candidate.path)?.path ?? item.renderVideoPath;
      patchVideoItem(item.id, {
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
      patchVideoItem(item.id, { videoCandidates: [{ index: 1, status: 'failed', path: null, error: candidateErrorMessage(error) }] });
      setVideoBulkFailedCount(1);
      setVideoPromptStatus(`${item.id} 動画生成失敗`);
    } finally {
      patchVideoItem(item.id, { videoGenerating: false });
      setVideoPromptBusy(false);
    }
  }, [ensureVideoItemsInState, generateVideoRequest, materializeVideoPrompts, narrationReadyForVideo, patchVideoItem, runId]);

  const generateVideoItems = useCallback(async (targetItems: EditableItem[]) => {
    if (!runId || !targetItems.length) return;
    if (!narrationReadyForVideo) {
      setVideoPromptStatus('動画生成には全編音声承認が必要です');
      return;
    }
    ensureVideoItemsInState(targetItems);
    const targetIds = new Set(targetItems.map((item) => item.id));
    const concurrency = Math.min(2, Math.max(targetItems.length, 1));
    setVideoPromptBusy(true);
    setVideoPromptStatus(`動画生成中 0/${targetItems.length}`);
    setVideoBulkTotal(targetItems.length);
    setVideoBulkCompletedCount(0);
    setVideoBulkFailedCount(0);
    setVideoTargetItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, videoGenerating: true, videoCandidates: [] } : item)));

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
        setVideoTargetItems((prev) =>
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
        setVideoTargetItems((prev) =>
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
      await materializeVideoPrompts(targetItems);
      await Promise.all(Array.from({ length: concurrency }, () => runNext()));
      setVideoPromptStatus(`動画生成完了 ${completed}/${targetItems.length}`);
    } catch (error) {
      console.error(error);
      const message = candidateErrorMessage(error);
      setVideoTargetItems((prev) => prev.map((item) => (
        targetIds.has(item.id)
          ? { ...item, videoGenerating: false, videoCandidates: [{ index: 1, status: 'failed', path: null, error: message }] }
          : item
      )));
      setVideoBulkFailedCount(targetItems.length);
      setVideoPromptStatus('動画プロンプト確定に失敗');
    } finally {
      setVideoPromptBusy(false);
    }
  }, [ensureVideoItemsInState, generateVideoRequest, materializeVideoPrompts, narrationReadyForVideo, runId]);

  const generateAllVideos = useCallback(async () => {
    if (!narrationReadyForVideo) {
      setVideoPromptStatus('動画生成には全編音声承認が必要です');
      setConfirmVideoPromptOpen(false);
      return;
    }
    if (!videoTargetItems.length) return;
    setConfirmVideoPromptOpen(false);
    await generateVideoItems(videoTargetItems);
  }, [generateVideoItems, narrationReadyForVideo, videoTargetItems]);

  const createNarrationDrafts = useCallback(async (replace = false) => {
    if (!runId) return;
    const targetRunId = runId;
    setConfirmNarrationReplaceOpen(false);
    setNarrationDraftBusy(true);
    setNarrationStatus(replace ? 'ナレーション文面を再作成中' : 'ナレーション文面を作成中');
    try {
      const data = await runNarrationMutation(targetRunId, async () => {
        try {
          return await jsonFetch<NarrationDraftCreateResponse>('/api/image-gen/narration-drafts/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              run_id: targetRunId,
              note: 'frontend narration draft creation',
              replace,
            }),
          });
        } finally {
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      const workspaceNote = data.authoringWorkspace?.status === 'ready'
        ? '。全編音声設計ワークスペースも準備しました'
        : data.authoringWorkspace?.warning ? `。音声設計準備: ${data.authoringWorkspace.warning}` : '';
      setNarrationStatus(`ナレーション文面 ${data.updated.length} cut 作成${workspaceNote}`);
    } catch (error) {
      console.error(error);
      setNarrationStatus(replace ? 'ナレーション文面の再作成に失敗' : 'ナレーション文面の作成に失敗');
    } finally {
      setNarrationDraftBusy(false);
    }
  }, [loadRunRequests, runId, runNarrationMutation]);

  const saveNarrationText = useCallback(async (item: EditableItem, lock: boolean): Promise<NarrationWorkflowItem | null> => {
    if (!runId) return null;
    const targetRunId = runId;
    patchItem(item.id, { narrationSaving: true });
    setNarrationStatus(`${item.id} ${lock ? '文面を確定中' : '下書きを保存中'}`);
    try {
      const data = await runNarrationMutation(targetRunId, async () => {
        try {
          const response = await jsonFetch<NarrationTextSaveResponse>('/api/image-gen/narration-text/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              run_id: targetRunId,
              item_id: item.id,
              text: item.narrationText,
              tts_text: item.narrationTtsText || item.narrationText,
              tool: item.narrationTool,
              authoring_status: lock ? 'human_locked' : 'draft',
              expected_revision: item.narrationRevision,
            }),
          });
          patchItem(item.id, narrationWorkflowPatch(response.item));
          return response;
        } finally {
          patchItem(item.id, { narrationSaving: false });
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      setNarrationStatus(`${item.id} ${lock ? '文面を確定しました' : '下書きを保存しました'}`);
      return data.item;
    } catch (error) {
      console.error(error);
      patchItem(item.id, { narrationSaving: false });
      setNarrationStatus(`${item.id} 保存に失敗しました。別タブ更新時は再読込してください`);
      return null;
    }
  }, [loadRunRequests, patchItem, runId, runNarrationMutation]);

  const confirmSilentOk = useCallback(async (item: EditableItem) => {
    if (!runId) return;
    const targetRunId = runId;
    patchItem(item.id, { narrationGenerating: true });
    setNarrationStatus(`${item.id} 無音OKを保存中`);
    try {
      await runNarrationMutation(targetRunId, async () => {
        try {
          await jsonFetch<NarrationSilentOkResponse>('/api/image-gen/narration-silent-ok', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              run_id: targetRunId,
              item_id: item.id,
              reason: 'frontend confirmed intentional silence',
              expected_revision: item.narrationRevision,
            }),
          });
        } finally {
          patchItem(item.id, { narrationGenerating: false });
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      setNarrationStatus(`${item.id} 無音OK`);
    } catch (error) {
      console.error(error);
      patchItem(item.id, { narrationGenerating: false });
      setNarrationStatus(`${item.id} 無音OKの保存に失敗`);
    }
  }, [loadRunRequests, patchItem, runId, runNarrationMutation]);

  const narrationPayload = useCallback((item: EditableItem) => ({
    item_id: item.id,
    tool: item.narrationTool,
    expected_revision: item.narrationRevision,
    expected_tts_hash: item.narrationTtsHash,
  }), []);

  const applyNarrationResult = useCallback((result: NarrationGenerateResponse['item']) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === result.itemId
          ? {
              ...item,
              narrationGenerating: false,
              narrationStatus: item.narrationAudioHumanApproved ? item.narrationStatus : result.status,
              narrationGenerationStatus: result.status,
              narrationCandidateId: result.candidateId || item.narrationCandidateId,
              narrationCandidateOutput: result.path || item.narrationCandidateOutput,
              narrationCandidateStatus: result.status,
              narrationCandidateExists: Boolean(result.path) && result.status !== 'failed',
              narrationCandidateDurationSec: result.durationSeconds ?? item.narrationCandidateDurationSec,
              narrationGeneratedFromTtsHash: result.generatedFromTtsHash || item.narrationGeneratedFromTtsHash,
              narrationAudioReviewStatus: item.narrationAudioReviewStatus,
              narrationAudioHumanApproved: item.narrationAudioHumanApproved,
              narrationExists: item.narrationExists,
              narrationOutput: item.narrationOutput,
              renderNarrationPath: item.renderNarrationPath,
            }
          : item,
      ),
    );
  }, []);

  const generateNarrationForCut = useCallback(async (item: EditableItem) => {
    if (!runId) return;
    const targetRunId = runId;
    let generationItem = item;
    if (item.narrationDirty || item.narrationRevision === 0) {
      const saved = await saveNarrationText(item, itemNarrationTextLocked(item));
      if (!saved) return;
      generationItem = { ...item, ...narrationWorkflowPatch(saved) } as EditableItem;
    }
    ensureItemsInState([item]);
    setActiveItemId(item.id);
    setNarrationBusy(true);
    setNarrationStatus(`音声生成中 ${item.id}`);
    setNarrationBulkTotal(1);
    setNarrationBulkCompletedCount(0);
    setNarrationBulkFailedCount(0);
    patchItem(item.id, { narrationGenerating: true });
    try {
      const data = await runNarrationMutation(targetRunId, async () => {
        try {
          const response = await jsonFetch<NarrationGenerateResponse>('/api/image-gen/narration-generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ run_id: targetRunId, ...narrationPayload(generationItem) }),
          });
          applyNarrationResult(response.item);
          return response;
        } finally {
          patchItem(item.id, { narrationGenerating: false });
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      const ok = data.item.status === 'candidate';
      setNarrationBulkCompletedCount(ok ? 1 : 0);
      setNarrationBulkFailedCount(ok ? 0 : 1);
      setNarrationStatus(ok ? `${item.id} 音声候補を生成しました。試聴後に承認してください` : `${item.id} 音声候補は古いrevisionです`);
    } catch (error) {
      console.error(error);
      patchItem(item.id, { narrationGenerating: false });
      setNarrationBulkFailedCount(1);
      setNarrationStatus(`${item.id} 音声生成失敗`);
    } finally {
      setNarrationBusy(false);
    }
  }, [applyNarrationResult, ensureItemsInState, loadRunRequests, narrationPayload, patchItem, runId, runNarrationMutation, saveNarrationText]);

  const approveNarrationCandidate = useCallback(async (item: EditableItem) => {
    if (!runId || !item.narrationCandidateId) return;
    const targetRunId = runId;
    patchItem(item.id, { narrationApproving: true });
    setNarrationStatus(`${item.id} 音声候補を承認中`);
    try {
      await runNarrationMutation(targetRunId, async () => {
        try {
          const data = await jsonFetch<NarrationAudioApproveResponse>('/api/image-gen/narration-audio/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              run_id: targetRunId,
              item_id: item.id,
              candidate_id: item.narrationCandidateId,
              expected_revision: item.narrationRevision,
              expected_tts_hash: item.narrationTtsHash,
              note: 'frontend listened to and approved this narration candidate',
            }),
          });
          const duration = data.item.approvedCandidate?.duration_seconds || data.item.candidate?.duration_seconds || 0;
          patchItem(item.id, {
            ...narrationWorkflowPatch(data.item),
            videoDurationSec: Math.max(item.videoDurationSec, Math.ceil(duration), 1),
            renderVideoDurationSec: Math.max(item.renderVideoDurationSec, Math.ceil(duration), 1),
          });
        } finally {
          patchItem(item.id, { narrationApproving: false });
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      setNarrationStatus(`${item.id} 音声を承認しました`);
    } catch (error) {
      console.error(error);
      patchItem(item.id, { narrationApproving: false });
      setNarrationStatus(`${item.id} 音声承認に失敗しました。revisionを確認してください`);
    }
  }, [loadRunRequests, patchItem, runId, runNarrationMutation]);

  const generateAllNarration = useCallback(async () => {
    if (!runId) return;
    const targetRunId = runId;
    const sceneItems = items.filter(
      (item) => isSceneCutItem(item)
        && item.narrationTool !== 'silent'
        && itemNarrationTextLocked(item)
        && !item.narrationDirty
        && item.narrationRevision > 0
        && !itemNarrationAudioReady(item),
    );
    if (!sceneItems.length && items.some(isSceneCutItem)) {
      setNarrationStatus('生成対象がありません。先に各cutの文面を確定してください');
      return;
    }
    if (!sceneItems.length) return;
    ensureItemsInState(sceneItems);
    const targetIds = new Set(sceneItems.map((item) => item.id));
    setNarrationBusy(true);
    setNarrationStatus(`音声生成中 0/${sceneItems.length}`);
    setNarrationBulkTotal(sceneItems.length);
    setNarrationBulkCompletedCount(0);
    setNarrationBulkFailedCount(0);
    setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, narrationGenerating: true } : item)));
    try {
      const data = await runNarrationMutation(targetRunId, async () => {
        try {
          const response = await jsonFetch<BulkNarrationGenerateResponse>('/api/image-gen/narration-generate-bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              run_id: targetRunId,
              items: sceneItems.map((item) => narrationPayload(item)),
              concurrency: 2,
            }),
          });
          response.results.forEach(applyNarrationResult);
          return response;
        } finally {
          setItems((prev) => prev.map((current) => (targetIds.has(current.id) ? { ...current, narrationGenerating: false } : current)));
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      let completed = 0;
      let failed = 0;
      data.results.forEach((result) => {
        if (result.status === 'candidate') completed += 1;
        else failed += 1;
      });
      setNarrationBulkCompletedCount(completed);
      setNarrationBulkFailedCount(failed);
      setNarrationStatus(`音声候補生成完了 ${completed}/${sceneItems.length}。試聴後に個別承認してください`);
    } catch (error) {
      console.error(error);
      setItems((prev) => prev.map((item) => (targetIds.has(item.id) ? { ...item, narrationGenerating: false } : item)));
      setNarrationBulkFailedCount(sceneItems.length);
      setNarrationStatus('音声生成失敗');
    } finally {
      setNarrationBusy(false);
    }
  }, [applyNarrationResult, ensureItemsInState, items, loadRunRequests, narrationPayload, runId, runNarrationMutation]);

  const runNarrationTextReview = useCallback(async () => {
    if (!runId || !allNarrationTextReady) {
      setNarrationStatus('全cutの文面を確定してからp720全編レビューを実行してください');
      return;
    }
    const targetRunId = runId;
    setNarrationReviewBusy(true);
    setNarrationStatus('p720 全編テキストレビュー中');
    try {
      const data = await runNarrationMutation(targetRunId, async () => {
        try {
          const response = await jsonFetch<NarrationReviewRunResponse>('/api/image-gen/narration-review/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ run_id: targetRunId }),
          });
          setNarrationReviewFindings(response.findings || []);
          setNarrationReviewReport(response.report || '');
          return response;
        } finally {
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      if (data.status === 'passed') {
        setNarrationStatus('p720 全編テキストレビュー合格');
      } else {
        const firstFinding = data.findings[0] ? `: ${data.findings[0]}` : '';
        setNarrationStatus(`p720 要修正${firstFinding}`);
      }
    } catch (error) {
      console.error(error);
      setNarrationReviewFindings([]);
      setNarrationStatus('p720 全編テキストレビューに失敗しました');
    } finally {
      setNarrationReviewBusy(false);
    }
  }, [allNarrationTextReady, loadRunRequests, runId, runNarrationMutation]);

  const playFullNarration = useCallback(async () => {
    if (!runId || !allNarrationAudioReady || !narrationAudioSetHash) {
      setNarrationStatus('先に全cutのcurrent音声を個別承認してください');
      return;
    }
    cancelFullNarrationPlayback();
    const token = fullNarrationPlaybackTokenRef.current + 1;
    fullNarrationPlaybackTokenRef.current = token;
    const audioSetHash = narrationAudioSetHash;
    const timeline = narrationApprovalTimeline.map((item) => ({ ...item }));
    let cutStartSeconds = 0;
    const schedule = sceneCutItems.map((item, index) => {
      const timelineItem = timeline[index];
      if (!timelineItem || timelineItem.item_id !== item.id) {
        throw new Error(`${item.id}: narration timeline order mismatch`);
      }
      const scheduledItem = { item, timelineItem, cutStartSeconds };
      cutStartSeconds += timelineItem.video_duration_seconds;
      return scheduledItem;
    });
    const totalDurationSeconds = cutStartSeconds;
    setFullNarrationListenEvidence(null);
    setFullNarrationListening(true);
    setFullNarrationListeningItem('準備中');
    setNarrationStatus('全編音声を事前読込中');
    document.querySelectorAll('audio').forEach((audio) => audio.pause());
    const audioContext = new AudioContext();
    const abortController = new AbortController();
    const activeSources = new Set<AudioBufferSourceNode>();
    let completionSource: ConstantSourceNode | null = null;
    let resolveCompletion: ((completed: boolean) => void) | null = null;
    let listeningItemTimer: number | null = null;
    let cancelled = false;
    const cancelThisPlayback = () => {
      cancelled = true;
      abortController.abort();
      activeSources.forEach((source) => {
        try {
          source.stop();
        } catch {
          // A source may have already ended.
        }
      });
      activeSources.clear();
      if (completionSource) {
        try {
          completionSource.stop();
        } catch {
          // The completion marker may have already ended.
        }
      }
      resolveCompletion?.(false);
      resolveCompletion = null;
      if (listeningItemTimer !== null) window.clearInterval(listeningItemTimer);
      listeningItemTimer = null;
      void audioContext.close().catch(() => undefined);
    };
    cancelCurrentFullNarrationAudioRef.current = cancelThisPlayback;

    try {
      await audioContext.resume();
      const decodedAudio = await Promise.all(schedule.map(async ({ item, timelineItem }) => {
        if (item.narrationTool === 'silent') return null;
        if (!item.narrationOutput) throw new Error(`${item.id}: approved narration output is missing`);
        const response = await fetch(audioFileUrl(runId, item.narrationOutput), { signal: abortController.signal });
        if (!response.ok) throw new Error(`full narration audio fetch failed: ${response.status}`);
        const buffer = await audioContext.decodeAudioData(await response.arrayBuffer());
        const availableDuration = timelineItem.video_duration_seconds - timelineItem.narration_offset_seconds;
        if (buffer.duration > availableDuration + 0.05) {
          throw new Error(`${item.id}: approved narration exceeds its timeline duration`);
        }
        return buffer;
      }));
      if (cancelled || fullNarrationPlaybackTokenRef.current !== token) return;

      const scheduleStartTime = audioContext.currentTime + 0.1;
      schedule.forEach(({ timelineItem, cutStartSeconds: itemStartSeconds }, index) => {
        const buffer = decodedAudio[index];
        if (!buffer) return;
        const source = audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(audioContext.destination);
        source.onended = () => activeSources.delete(source);
        activeSources.add(source);
        source.start(scheduleStartTime + itemStartSeconds + timelineItem.narration_offset_seconds);
      });

      const completionGain = audioContext.createGain();
      completionGain.gain.value = 0;
      completionGain.connect(audioContext.destination);
      completionSource = audioContext.createConstantSource();
      completionSource.offset.value = 0;
      completionSource.connect(completionGain);
      const completion = new Promise<boolean>((resolve) => {
        let settled = false;
        resolveCompletion = (completed) => {
          if (settled) return;
          settled = true;
          resolve(completed);
        };
        completionSource!.onended = () => {
          resolveCompletion?.(!cancelled && fullNarrationPlaybackTokenRef.current === token);
        };
      });
      completionSource.start(scheduleStartTime);
      completionSource.stop(scheduleStartTime + totalDurationSeconds);

      const updateListeningItem = () => {
        const elapsedSeconds = Math.max(0, audioContext.currentTime - scheduleStartTime);
        const current = schedule.find(({ timelineItem, cutStartSeconds: itemStartSeconds }) => (
          elapsedSeconds < itemStartSeconds + timelineItem.video_duration_seconds
        ));
        setFullNarrationListeningItem(current?.item.id || schedule.at(-1)?.item.id || '');
      };
      updateListeningItem();
      listeningItemTimer = window.setInterval(updateListeningItem, 100);
      setNarrationStatus('全編音声を承認タイムラインどおりに再生中');

      const completed = await completion;
      resolveCompletion = null;
      if (!completed || fullNarrationPlaybackTokenRef.current !== token) return;
      setFullNarrationListenEvidence({
        mode: 'sequential_full_run',
        audio_set_hash: audioSetHash,
        item_ids: schedule.map(({ item }) => item.id),
        timeline,
        completed_at: new Date().toISOString(),
      });
      setNarrationStatus('全編音声の通し試聴が完了しました');
    } catch (error) {
      console.error(error);
      if (!cancelled && fullNarrationPlaybackTokenRef.current === token) {
        setFullNarrationListenEvidence(null);
        setNarrationStatus('全編音声の通し試聴に失敗しました');
      }
    } finally {
      if (listeningItemTimer !== null) window.clearInterval(listeningItemTimer);
      if (cancelCurrentFullNarrationAudioRef.current === cancelThisPlayback) {
        cancelCurrentFullNarrationAudioRef.current = null;
      }
      if (audioContext.state !== 'closed') {
        await audioContext.close().catch(() => undefined);
      }
      if (fullNarrationPlaybackTokenRef.current === token) {
        setFullNarrationListening(false);
        setFullNarrationListeningItem('');
      }
    }
  }, [
    allNarrationAudioReady,
    cancelFullNarrationPlayback,
    narrationApprovalTimeline,
    narrationAudioSetHash,
    runId,
    sceneCutItems,
  ]);

  const approveFullNarration = useCallback(async () => {
    if (!runId || !narrationAudioSetHash) return;
    if (narrationDurationLimitViolation) {
      setNarrationStatus(`${narrationDurationLimitViolation.item_id}: 60秒を超えています。短いcutへ分割してください`);
      return;
    }
    if (!narrationTextReviewPassed) {
      setNarrationStatus('先にp720全編テキストレビューを合格させてください');
      return;
    }
    if (!fullNarrationListenIsCurrent || !fullNarrationListenEvidence) {
      setNarrationStatus('currentな全編音声を最初から最後まで通し試聴してください');
      return;
    }
    const targetRunId = runId;
    setNarrationBusy(true);
    setNarrationStatus('全編音声を承認中');
    try {
      await runNarrationMutation(targetRunId, async () => {
        try {
          await jsonFetch<NarrationRunApproveResponse>('/api/image-gen/narration-review/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              run_id: targetRunId,
              note: 'frontend reviewed and approved the complete narration track',
              expected_audio_set_hash: narrationAudioSetHash,
              timeline: narrationApprovalTimeline,
              listen_evidence: fullNarrationListenEvidence,
            }),
          });
        } finally {
          await loadRunRequests(targetRunId, 'scene');
        }
      });
      setNarrationStatus('全編音声を承認しました。動画生成へ進めます');
    } catch (error) {
      console.error(error);
      setNarrationStatus('全編音声を承認できません。未承認cutまたは尺を確認してください');
    } finally {
      setNarrationBusy(false);
    }
  }, [
    fullNarrationListenEvidence,
    fullNarrationListenIsCurrent,
    narrationApprovalTimeline,
    narrationAudioSetHash,
    narrationDurationLimitViolation,
    narrationTextReviewPassed,
    loadRunRequests,
    runId,
    runNarrationMutation,
  ]);

  const buildRenderItems = useCallback((targetItems: EditableItem[]) => targetItems.map((item) => ({
    item_id: item.id,
    video_path: item.renderVideoPath,
    narration_path: itemNarrationAudioReady(item) && item.narrationTool === 'silent' && !item.narrationExists ? null : item.renderNarrationPath || item.narrationOutput,
    video_duration_seconds: Math.max(item.renderVideoDurationSec, Math.ceil((item.narrationDurationSec || 0) + item.renderNarrationOffsetSec), 1),
    narration_offset_seconds: item.renderNarrationOffsetSec,
  })), []);

  const freezeRenderInputs = useCallback(async () => {
    if (!runId || !visibleItems.length || !narrationReadyForVideo) {
      setRenderStatus('入力確定にはcurrentな全編音声承認が必要です');
      return;
    }
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
  }, [buildRenderItems, narrationReadyForVideo, runId, saveCurrentReview, visibleItems]);

  const finalRender = useCallback(async () => {
    if (!runId || !visibleItems.length || !narrationReadyForVideo) {
      setRenderStatus('最終レンダーにはcurrentな全編音声承認が必要です');
      return;
    }
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
  }, [buildRenderItems, narrationReadyForVideo, runId, saveCurrentReview, visibleItems]);

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
      videoDirtyFields: [],
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
      narrationStatus: '',
      narrationReviewStatus: '',
      narrationAuthoringStatus: 'missing',
      narrationRevision: 0,
      narrationTextHash: '',
      narrationTtsHash: '',
      narrationGenerationStatus: 'missing',
      narrationCandidateId: null,
      narrationCandidateOutput: null,
      narrationCandidateStatus: '',
      narrationCandidateExists: false,
      narrationCandidateDurationSec: null,
      narrationGeneratedFromTtsHash: '',
      narrationAudioReviewStatus: 'pending',
      narrationAudioHumanApproved: false,
      narrationDirty: false,
      narrationSaving: false,
      narrationApproving: false,
      narrationSilentOk: false,
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
    const targetDurationSeconds = Number(createRunTargetDurationSeconds);
    if (!Number.isInteger(targetDurationSeconds) || targetDurationSeconds < 300 || targetDurationSeconds > 1200) return;
    const mode = createRunMode;
    const endpoint = mode === 'scene_storyboard' ? '/api/image-gen/runs/create/storyboard' : '/api/image-gen/runs/create';
    setCreateRunBusy(true);
    setCreateRunError(null);
    setCreateRunStatus('フォルダを作成中');
    try {
      const created = await jsonFetch<CreateRunJob>(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          source: createRunSource.trim() || null,
          target_duration_seconds: targetDurationSeconds,
        }),
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
      setCreateRunMode('normal');
      setCreateRunTargetDurationSeconds('300');
      setCreateRunStatus(mode === 'scene_storyboard' ? 'ストーリーボード式ToCを作成中' : 'ToCを作成中');

      let latest = created;
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await sleep(60000);
        latest = await jsonFetch<CreateRunJob>(`/api/image-gen/runs/create/${encodeURIComponent(created.jobId)}`);
        if (latest.message) setCreateRunStatus(latest.message);
        if (latest.status === 'completed' || latest.status === 'failed' || latest.status === 'paused') break;
      }
      if (latest.status !== 'completed' && latest.status !== 'paused') {
        throw new Error(latest.error || '作成が完了しませんでした');
      }
      setCreateRunStatus(latest.status === 'paused' ? `${latest.currentProcess || 'p650'}で中断` : '作成完了');
      await loadRuns(created.runId);
      await loadRunRequests(created.runId, workspaceMode === 'image' ? viewKind : 'scene');
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
                <Select value={runId} label="出力先" onChange={(event) => setRunId(event.target.value)} disabled={busy || generationInFlight}>
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
              <Tooltip title="現在の出力を再取得">
                <IconButton onClick={refreshCurrentRun} color="primary" aria-label="現在の出力を再取得" disabled={!runId || busy}>
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
              <Tabs value={workspaceMode} onChange={(_, value) => switchWorkspaceMode(value as WorkspaceMode)} className="tabs workspaceTabs compactTabs">
                <Tab value="image" label="画像" />
                <Tab value="narration" label="音声" />
                <Tab value="video" label="動画" />
                <Tab value="render" label="最終" />
              </Tabs>

              {workspaceMode === 'image' ? (
                <>
                  <Tabs value={viewKind} onChange={(_, value) => setViewKind(value)} className="tabs viewTabs compactTabs">
                    <Tab value="asset" label="素材" />
                    <Tab value="scene" label="シーン" />
                  </Tabs>
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
                    min={1}
                    max={16}
                    step={0.1}
                    value={candidateCountDraft}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(value) => `${Math.round(value)}候補`}
                    shiftStep={1}
                    onChange={(_, value) => setCandidateCountDraft(value as number)}
                    onChangeCommitted={(_, value) => {
                      const nextCount = Math.round(value as number);
                      setCandidateCount(nextCount);
                      setCandidateCountDraft(nextCount);
                    }}
                    marks={[
                      { value: 1, label: '1' },
                      { value: 8, label: '8' },
                      { value: 16, label: '16' },
                    ]}
                  />
                </>
              ) : workspaceMode === 'narration' ? (
                <>
                  <Typography variant="caption" className="stationLabel">p720 / p750</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography fontWeight={800}>全cutナレーション</Typography>
                    <Chip color={allNarrationAudioReady ? 'success' : 'primary'} label={`${narrationAudioReadyCount}/${sceneCutItems.length}`} />
                  </Stack>
                  {narrationDurationLimitViolation && (
                    <Chip
                      size="small"
                      color="error"
                      label={`${narrationDurationLimitViolation.item_id}: 60秒以内のcutへ分割してください`}
                    />
                  )}
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant={hasNarrationDrafts ? 'outlined' : 'contained'}
                      startIcon={<RecordVoiceOverIcon />}
                      onClick={() => (hasNarrationDrafts ? setConfirmNarrationReplaceOpen(true) : createNarrationDrafts(false))}
                      disabled={!sceneCutItems.length || narrationDraftBusy || narrationBusy || narrationMutationActive || fullNarrationListening}
                    >
                      {hasNarrationDrafts ? '未確定文面を再作成' : '文面枠を作成'}
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<FactCheckIcon />}
                      onClick={runNarrationTextReview}
                      disabled={!allNarrationTextReady || narrationReviewBusy || narrationBusy || narrationDraftBusy || narrationMutationActive || fullNarrationListening}
                    >
                      {narrationTextReviewPassed ? 'p720再レビュー' : 'p720全編レビュー'}
                    </Button>
                    <Button
                      variant="contained"
                      startIcon={<RecordVoiceOverIcon />}
                      onClick={generateAllNarration}
                      disabled={
                        !visibleItems.length
                        || !sceneCutItems.some((item) => itemNarrationTextLocked(item) && !item.narrationDirty && !itemNarrationAudioReady(item))
                        || narrationBusy
                        || narrationDraftBusy
                        || narrationMutationActive
                        || fullNarrationListening
                      }
                    >
                      音声候補を生成
                    </Button>
                    <Button
                      variant={fullNarrationListenIsCurrent ? 'outlined' : 'contained'}
                      startIcon={fullNarrationListening ? <StopIcon /> : <PlayArrowIcon />}
                      onClick={fullNarrationListening ? cancelFullNarrationPlayback : playFullNarration}
                      disabled={!fullNarrationListening && (!allNarrationAudioReady || !narrationAudioSetHash || narrationBusy || narrationReviewBusy || narrationMutationActive)}
                    >
                      {fullNarrationListening ? `停止 ${fullNarrationListeningItem}` : fullNarrationListenIsCurrent ? '通し試聴済み' : '全編を通し試聴'}
                    </Button>
                    <Button color="success" variant="contained" onClick={approveFullNarration} disabled={!allNarrationAudioReady || !narrationAudioSetHash || !narrationTextReviewPassed || !fullNarrationListenIsCurrent || narrationRunApproved || narrationBusy || narrationReviewBusy || narrationMutationActive || fullNarrationListening}>
                      {narrationRunApproved ? '全編承認済み' : '全編承認'}
                    </Button>
                  </Stack>
                </>
              ) : workspaceMode === 'render' ? (
                <>
                  <Typography variant="caption" className="stationLabel">最終レンダー</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography fontWeight={800}>結合入力</Typography>
                    <Chip color="primary" label={`${visibleItems.length} cut`} />
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    <Button variant="outlined" startIcon={<FactCheckIcon />} onClick={freezeRenderInputs} disabled={!visibleItems.length || !narrationReadyForVideo || renderBusy}>
                      入力確定
                    </Button>
                    <Button variant="contained" startIcon={<MovieCreationIcon />} onClick={finalRender} disabled={!visibleItems.length || !narrationReadyForVideo || renderBusy}>
                      最終レンダー
                    </Button>
                  </Stack>
                </>
              ) : (
                <>
                  <Typography variant="caption" className="stationLabel">動画生成本数</Typography>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography fontWeight={800}>同時生成本数</Typography>
                    <Chip color={narrationReadyForVideo ? 'primary' : 'default'} label={narrationReadyForVideo ? `${displayedVideoCandidateCount}候補` : `音声承認 ${narrationAudioReadyCount}/${sceneCutItems.length}`} />
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
                    disabled={!visibleItems.length || !narrationReadyForVideo || videoPromptBusy}
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
                {viewKind === 'asset' && (
                  <Box className="sceneCutTabsBar assetFilterTabsBar">
                    <Tabs
                      value={assetFilter}
                      onChange={(_, value) => setAssetFilter(value as AssetFilter)}
                      className="tabs sceneCutTabs"
                      variant="scrollable"
                      scrollButtons="auto"
                    >
                      <Tab value="asset" label="全素材" />
                      <Tab value="chara" label="キャラクター" />
                      <Tab value="obj" label="アイテム" />
                      <Tab value="location" label="場所" />
                    </Tabs>
                    <Chip size="small" color="primary" label={`${visibleItems.length}件`} />
                  </Box>
                )}
                {viewKind === 'scene' && imageSceneGroups.length > 0 && (
                  <Box className="sceneCutTabsBar imageSceneTabsBar">
                    <Tabs
                      value={activeImageScene?.key || ''}
                      onChange={(_, value) => setActiveImageSceneKey(value as string)}
                      className="tabs sceneCutTabs"
                      variant="scrollable"
                      scrollButtons="auto"
                    >
                      {imageSceneGroups.map((group) => (
                        <Tab key={group.key} value={group.key} label={`${group.label} / ${group.items.length}`} />
                      ))}
                    </Tabs>
                    <Chip size="small" color="primary" label={`${imageSceneItems.length}/${visibleItems.length} cut`} />
                  </Box>
                )}
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
                {viewKind === 'scene' && activeImageCutItem ? (
                  <Box className="sceneCutPager" aria-label="シーン内cut移動">
                    <PromptCard
                      key={activeImageCutItem.id}
                      item={activeImageCutItem}
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
                    <Tooltip title="前のcut">
                      <span className="sceneCutOverlayButton sceneCutOverlayButtonLeft">
                        <IconButton
                          color="primary"
                          onClick={() => moveImageCut(-1)}
                          disabled={!canGoPrevImageCut}
                          aria-label="前のcutへ移動"
                        >
                          <KeyboardArrowLeftIcon />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="次のcut">
                      <span className="sceneCutOverlayButton sceneCutOverlayButtonRight">
                        <IconButton
                          color="primary"
                          onClick={() => moveImageCut(1)}
                          disabled={!canGoNextImageCut}
                          aria-label="次のcutへ移動"
                        >
                          <KeyboardArrowRightIcon />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Box>
                ) : imageDisplayItems.map((item) => (
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
                    <Chip size="small" color="primary" label={`${videoDisplayItems.length}/${videoTargetItems.length} 動画target`} />
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
                {workspaceMode === 'video' && !narrationReadyForVideo && (
                  <GlassPanel variant="frosted" density="spacious" className="emptyGallery narrationGateCard">
                    <Typography fontWeight={900}>動画生成には音声レビューが必要です</Typography>
                    <Typography variant="body2" color="text.secondary">
                      音声タブで各cutの候補を承認し、最後に「全編音声を承認」してください。
                    </Typography>
                    <Chip color="primary" label={`音声 ${narrationAudioReadyCount}/${sceneCutItems.length}`} />
                  </GlassPanel>
                )}
                {workspaceMode === 'narration' && narrationReviewFindings.length > 0 && (
                  <GlassPanel variant="frosted" density="spacious" className="emptyGallery narrationGateCard">
                    <Typography fontWeight={900}>p720 全編レビューの修正点</Typography>
                    <Stack spacing={0.75}>
                      {narrationReviewFindings.slice(0, 20).map((finding, index) => (
                        <Typography key={`${index}-${finding}`} variant="body2" color="error">
                          {finding}
                        </Typography>
                      ))}
                    </Stack>
                    {narrationReviewReport && (
                      <Typography variant="caption" color="text.secondary">
                        詳細レポート: {narrationReviewReport}
                      </Typography>
                    )}
                  </GlassPanel>
                )}
                {workspaceMode === 'narration' && visibleItems.map((item) => (
                  <NarrationCutCard
                    key={item.id}
                    item={item}
                    runId={runId}
                    narrationBusy={narrationBusy || narrationDraftBusy || narrationReviewBusy || narrationMutationActive || fullNarrationListening}
                    onPatchItem={patchItem}
                    onSaveNarrationText={saveNarrationText}
                    onGenerateNarration={generateNarrationForCut}
                    onApproveNarration={approveNarrationCandidate}
                    onConfirmSilentOk={confirmSilentOk}
                  />
                ))}
                {workspaceMode === 'video' && videoDisplayItems.map((item) => (
                  <VideoCutCard
                    key={item.id}
                    item={item}
                    runId={runId}
                    references={references}
                    videoGenerationBusy={videoPromptBusy}
                    videoReady={narrationReadyForVideo}
                    videoCandidateCount={videoCandidateCount}
                    onPatchItem={patchVideoDraftItem}
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
              {workspaceMode === 'video' && videoPromptBusy && <Chip size="small" color="primary" label={`動画生成中 ${videoBulkCompletedCount + videoBulkFailedCount}/${videoBulkTotal || videoTargetItems.length}`} />}
              {workspaceMode === 'video' && !videoPromptBusy && videoBulkTotal > 0 && <Chip size="small" label={`動画生成完了 ${videoBulkCompletedCount + videoBulkFailedCount}/${videoBulkTotal}`} />}
              {workspaceMode === 'video' && videoBulkFailedCount > 0 && <Chip size="small" color="error" label={`動画失敗 ${videoBulkFailedCount}`} />}
              {workspaceMode === 'video' && !narrationReadyForVideo && <Chip size="small" color="warning" label={`音声承認待ち ${narrationAudioReadyCount}/${sceneCutItems.length}`} />}
              {workspaceMode === 'narration' && narrationDraftBusy && <Chip size="small" color="primary" label="文面作成中" />}
              {workspaceMode === 'narration' && !narrationDraftBusy && hasNarrationDrafts && <Chip size="small" color="primary" label={`文面 ${narrationDraftReadyCount}/${sceneCutItems.length}`} />}
              {workspaceMode === 'narration' && narrationBusy && <Chip size="small" color="primary" label={`音声生成中 ${narrationBulkCompletedCount + narrationBulkFailedCount}/${narrationBulkTotal || visibleItems.length}`} />}
              {workspaceMode === 'narration' && !narrationBusy && narrationBulkTotal > 0 && <Chip size="small" label={`音声生成完了 ${narrationBulkCompletedCount + narrationBulkFailedCount}/${narrationBulkTotal}`} />}
              {workspaceMode === 'narration' && narrationBulkFailedCount > 0 && <Chip size="small" color="error" label={`音声失敗 ${narrationBulkFailedCount}`} />}
              {workspaceMode === 'narration' && narrationReviewBusy && <Chip size="small" color="primary" label="p720全編レビュー中" />}
              {workspaceMode === 'narration' && fullNarrationListening && <Chip size="small" color="primary" label={`通し試聴中 ${fullNarrationListeningItem}`} />}
              {workspaceMode === 'narration' && fullNarrationListenIsCurrent && !fullNarrationListening && <Chip size="small" color="success" label="current全編試聴済み" />}
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
              {workspaceMode !== 'narration' && (
                <Button
                  variant="outlined"
                  startIcon={<SaveIcon />}
                  onClick={saveCurrentReview}
                  disabled={!(workspaceMode === 'video' ? videoTargetItems.length : visibleItems.length) || reviewSaveBusy}
                >
                  一時保存
                </Button>
              )}
              {workspaceMode === 'image' ? (
                <>
                  <Button variant="contained" startIcon={<AutoAwesomeIcon />} onClick={generateBulk} disabled={!imageBulkItems.length || bulkGenerating}>
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
                <Stack direction="row" spacing={1}>
                  <Button
                    variant={hasNarrationDrafts ? 'outlined' : 'contained'}
                    startIcon={<RecordVoiceOverIcon />}
                    onClick={() => (hasNarrationDrafts ? setConfirmNarrationReplaceOpen(true) : createNarrationDrafts(false))}
                    disabled={!sceneCutItems.length || narrationDraftBusy || narrationBusy || narrationMutationActive || fullNarrationListening}
                  >
                    {hasNarrationDrafts ? '未確定文面を再作成' : '文面枠を作成'}
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<FactCheckIcon />}
                    onClick={runNarrationTextReview}
                    disabled={!allNarrationTextReady || narrationReviewBusy || narrationBusy || narrationDraftBusy || narrationMutationActive || fullNarrationListening}
                  >
                    {narrationTextReviewPassed ? 'p720再レビュー' : 'p720全編レビュー'}
                  </Button>
                  <Button
                    className="insertAction"
                    variant="contained"
                    startIcon={<RecordVoiceOverIcon />}
                    onClick={generateAllNarration}
                    disabled={
                      !visibleItems.length
                      || !sceneCutItems.some((item) => itemNarrationTextLocked(item) && !item.narrationDirty && !itemNarrationAudioReady(item))
                      || narrationBusy
                      || narrationDraftBusy
                      || narrationMutationActive
                      || fullNarrationListening
                    }
                  >
                    確定済み文面の音声候補を生成
                  </Button>
                  <Button
                    variant={fullNarrationListenIsCurrent ? 'outlined' : 'contained'}
                    startIcon={fullNarrationListening ? <StopIcon /> : <PlayArrowIcon />}
                    onClick={fullNarrationListening ? cancelFullNarrationPlayback : playFullNarration}
                    disabled={!fullNarrationListening && (!allNarrationAudioReady || !narrationAudioSetHash || narrationBusy || narrationReviewBusy || narrationMutationActive)}
                  >
                    {fullNarrationListening ? `停止 ${fullNarrationListeningItem}` : fullNarrationListenIsCurrent ? '通し試聴済み' : '全編を通し試聴'}
                  </Button>
                  <Button
                    className="insertAction"
                    color="success"
                    variant="contained"
                    startIcon={<FactCheckIcon />}
                    onClick={approveFullNarration}
                    disabled={!allNarrationAudioReady || !narrationAudioSetHash || !narrationTextReviewPassed || !fullNarrationListenIsCurrent || narrationRunApproved || narrationBusy || narrationDraftBusy || narrationReviewBusy || narrationMutationActive || fullNarrationListening}
                  >
                    {narrationRunApproved ? '全編音声承認済み' : '全編音声を承認'}
                  </Button>
                </Stack>
              ) : workspaceMode === 'render' ? (
                <>
                  <Button variant="outlined" startIcon={<FactCheckIcon />} onClick={freezeRenderInputs} disabled={!visibleItems.length || !narrationReadyForVideo || renderBusy}>
                    入力確定
                  </Button>
                  <Button className="insertAction" variant="contained" startIcon={<MovieCreationIcon />} onClick={finalRender} disabled={!visibleItems.length || !narrationReadyForVideo || renderBusy}>
                    最終レンダー
                  </Button>
                </>
              ) : (
                <Button
                  className="insertAction"
                  variant="contained"
                  startIcon={<MovieCreationIcon />}
                  onClick={openVideoPromptConfirm}
                  disabled={!visibleItems.length || !narrationReadyForVideo || videoPromptBusy}
                >
                  全cut動画生成
                </Button>
              )}
              <Tooltip title="制作相談を開く">
                <IconButton
                  ref={chatToggleButtonRef}
                  className="chatToggleButton"
                  color="secondary"
                  onClick={() => setChatOpen(true)}
                  aria-label="制作相談を開く"
                  aria-expanded={chatOpen}
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
              <FormControl fullWidth size="small">
                <InputLabel>作成モード</InputLabel>
                <Select
                  label="作成モード"
                  value={createRunMode}
                  disabled={createRunBusy}
                  onChange={(event) => setCreateRunMode(event.target.value as CreateRunMode)}
                >
                  <MenuItem value="normal">通常</MenuItem>
                  <MenuItem value="scene_storyboard">1scene=1ストーリーボード式</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth size="small">
                <InputLabel>動画尺プリセット</InputLabel>
                <Select
                  label="動画尺プリセット"
                  value={['300', '600', '900', '1200'].includes(createRunTargetDurationSeconds) ? createRunTargetDurationSeconds : ''}
                  disabled={createRunBusy}
                  onChange={(event) => setCreateRunTargetDurationSeconds(String(event.target.value))}
                >
                  <MenuItem value="">カスタム</MenuItem>
                  <MenuItem value="300">5分</MenuItem>
                  <MenuItem value="600">10分</MenuItem>
                  <MenuItem value="900">15分</MenuItem>
                  <MenuItem value="1200">20分</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="目標動画尺（秒）"
                type="number"
                value={createRunTargetDurationSeconds}
                disabled={createRunBusy}
                onChange={(event) => setCreateRunTargetDurationSeconds(event.target.value)}
                slotProps={{ htmlInput: { min: 300, max: 1200, step: 1 } }}
                error={
                  !Number.isInteger(Number(createRunTargetDurationSeconds))
                  || Number(createRunTargetDurationSeconds) < 300
                  || Number(createRunTargetDurationSeconds) > 1200
                }
                helperText="300〜1200秒。実効尺は目標の80%以上で合格します。"
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
              disabled={
                createRunBusy
                || !createRunTitle.trim()
                || !Number.isInteger(Number(createRunTargetDurationSeconds))
                || Number(createRunTargetDurationSeconds) < 300
                || Number(createRunTargetDurationSeconds) > 1200
              }
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
                ? visibleItems.some((item) => item.executionLane !== 'existing_asset' && item.promptPolicyVersion === 'image_api_prompt_v2')
                  ? `${settingsTargetLabel(settingsTarget)}の表示中 ${visibleItems.filter((item) => item.executionLane !== 'existing_asset').length} 件について、上流のfirst-frame設計を更新し、manifest・prompt・snapshotを再コンパイルします。`
                  : `${settingsTargetLabel(settingsTarget)}の表示中 ${visibleItems.filter((item) => item.executionLane !== 'existing_asset').length} 件を、新しい指示で再生成します。`
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
          open={confirmNarrationReplaceOpen}
          onClose={() => setConfirmNarrationReplaceOpen(false)}
          className="settingsDialog"
          aria-labelledby="confirm-narration-replace-title"
        >
          <DialogTitle id="confirm-narration-replace-title">ナレーション文面を再作成しますか？</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={1.5}>
              <Typography>
                既存のナレーション文面、TTS文面、scene_narration_plan、無音設定、レビュー状態を上書きします。
              </Typography>
              <Typography variant="body2" color="text.secondary">
                既存の音声ファイルは削除しませんが、再作成後は文面と一致しない可能性があります。
              </Typography>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmNarrationReplaceOpen(false)}>キャンセル</Button>
            <Button variant="contained" color="warning" onClick={() => createNarrationDrafts(true)} disabled={narrationDraftBusy || narrationMutationActive}>
              再作成
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
                対象: {sceneCutItems.length} cut / 各cut {videoCandidateCount} 本を候補動画として並列生成します。
              </Typography>
              {!narrationReadyForVideo && (
                <Typography variant="body2" color="error">
                  動画生成には各cutの音声承認と全編音声承認が必要です。
                </Typography>
              )}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmVideoPromptOpen(false)}>キャンセル</Button>
            <Button variant="contained" startIcon={<MovieCreationIcon />} onClick={generateAllVideos} disabled={videoPromptBusy || !sceneCutItems.length || !narrationReadyForVideo}>
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
          aria-hidden={!chatOpen ? true : undefined}
          inert={!chatOpen ? true : undefined}
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
