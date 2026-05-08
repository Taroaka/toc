import React, { useEffect, useMemo, useRef, useState } from 'react';
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
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ArchiveIcon from '@mui/icons-material/Archive';
import ChatIcon from '@mui/icons-material/Chat';
import DownloadIcon from '@mui/icons-material/Download';
import ImageIcon from '@mui/icons-material/Image';
import SendIcon from '@mui/icons-material/Send';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import RefreshIcon from '@mui/icons-material/Refresh';
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
};

type EditableItem = ImageRequestItem & {
  draftPrompt: string;
  selectedReferences: ReferenceOption[];
  candidates: Candidate[];
  selectedCandidatePath: string | null;
  generating: boolean;
};

type ViewKind = 'asset' | 'scene';
type AssetFilter = 'chara' | 'obj' | 'asset';
type AssetCategory = 'chara' | 'obj' | 'asset';
type InsertStatus = 'idle' | 'running' | 'success' | 'error';

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0e1113',
      paper: '#171b1f',
    },
    primary: {
      main: '#8ee8ff',
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

async function jsonFetch<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

function toEditableItems(items: ImageRequestItem[], refs: ReferenceOption[]): EditableItem[] {
  const byPath = new Map(refs.map((ref) => [ref.path, ref]));
  return items.map((item) => ({
    ...item,
    draftPrompt: item.prompt,
    selectedReferences: item.references.map((ref) => byPath.get(ref)).filter(Boolean) as ReferenceOption[],
    candidates: [],
    selectedCandidatePath: null,
    generating: false,
  }));
}

function candidateErrorMessage(error: unknown): string {
  const text = String(error);
  if (text.includes('savedPath')) return 'savedPath missing';
  if (text.includes('reference')) return 'reference error';
  if (text.includes('disabled')) return 'app-server disabled';
  if (text.includes('timed out')) return 'generation timed out';
  return 'generation failed';
}

function executionLaneLabel(lane: string): string {
  const labels: Record<string, string> = {
    bootstrap_builtin: '参照なし生成',
    standard: '参照あり生成',
  };
  return labels[lane] ?? '生成設定あり';
}

function viewLabel(view: ViewKind): string {
  return view === 'scene' ? 'シーン' : '素材';
}

function assetFilterLabel(filter: AssetFilter): string {
  return { chara: 'キャラ', obj: '小物', asset: '全素材' }[filter];
}

function assetCategory(item: EditableItem): AssetCategory {
  const assetType = (item.assetType || '').toLowerCase();
  const output = (item.output || '').toLowerCase();
  if (assetType.includes('character') || output.startsWith('assets/characters/')) return 'chara';
  if (assetType.includes('object') || output.startsWith('assets/objects/')) return 'obj';
  return 'asset';
}

function assetCategoryRank(category: AssetCategory): number {
  return { chara: 0, obj: 1, asset: 2 }[category];
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

function App() {
  const [runs, setRuns] = useState<RunFolder[]>([]);
  const [runId, setRunId] = useState('');
  const [viewKind, setViewKind] = useState<ViewKind>('asset');
  const [assetFilter, setAssetFilter] = useState<AssetFilter>('asset');
  const [candidateCount, setCandidateCount] = useState(2);
  const [items, setItems] = useState<EditableItem[]>([]);
  const [references, setReferences] = useState<ReferenceOption[]>([]);
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
  const [insertBusy, setInsertBusy] = useState(false);
  const [insertStatus, setInsertStatus] = useState<InsertStatus>('idle');
  const [lastInsertedCount, setLastInsertedCount] = useState(0);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [insertedKeys, setInsertedKeys] = useState<Set<string>>(() => new Set());
  const mobileChatButtonRef = useRef<HTMLButtonElement | null>(null);
  const chatInputRef = useRef<HTMLInputElement | null>(null);
  const selectedRun = runs.find((run) => run.id === runId);
  const visibleItems = useMemo(
    () => (viewKind === 'scene' ? items : sortAssetItems(items.filter((item) => itemMatchesAssetFilter(item, assetFilter)))),
    [assetFilter, items, viewKind],
  );
  const breadcrumb = [viewLabel(viewKind), viewKind === 'asset' ? assetFilterLabel(assetFilter) : null]
    .filter(Boolean)
    .join(' / ');
  const activeItem = useMemo(
    () => visibleItems.find((item) => item.id === activeItemId) ?? visibleItems[0] ?? null,
    [activeItemId, visibleItems],
  );

  useEffect(() => {
    jsonFetch<{ runs: RunFolder[] }>('/api/image-gen/runs')
      .then((data) => {
        setRuns(data.runs);
        if (data.runs[0]) setRunId(data.runs[0].id);
      })
      .catch((error) => console.error(error));
  }, []);

  useEffect(() => {
    if (!runId) return;
    setBusy(true);
    jsonFetch<{ items: ImageRequestItem[]; references: ReferenceOption[] }>(
      `/api/image-gen/requests?run_id=${encodeURIComponent(runId)}&kind=${viewKind}`,
    )
      .then((data) => {
        setReferences(data.references);
        setItems(toEditableItems(data.items, data.references));
      })
      .catch((error) => {
        console.error(error);
        setItems([]);
        setReferences([]);
      })
      .finally(() => setBusy(false));
  }, [runId, viewKind]);

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

  const selectedForInsert = useMemo(
    () => items.filter((item) => item.selectedCandidatePath && item.output),
    [items],
  );
  const adoptedKeys = insertedKeys;

  const patchItem = (itemId: string, patch: Partial<EditableItem>) => {
    setItems((prev) => prev.map((item) => (item.id === itemId ? { ...item, ...patch } : item)));
  };

  const closeChat = () => {
    setChatOpen(false);
    if (isNarrowViewport) {
      window.setTimeout(() => mobileChatButtonRef.current?.focus(), 0);
    }
  };

  const generateItem = async (item: EditableItem) => {
    if (!runId) return;
    setActiveItemId(item.id);
    setInsertStatus('idle');
    patchItem(item.id, { generating: true, candidates: [] });
    try {
      const data = await jsonFetch<{ candidates: Candidate[] }>('/api/image-gen/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          kind: viewKind,
          item_id: item.id,
          prompt: item.draftPrompt,
          references: item.selectedReferences.map((ref) => ref.path),
          candidate_count: candidateCount,
        }),
      });
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
  };

  const generateBulk = async () => {
    if (!runId) return;
    const targetItems = [...visibleItems];
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
        const data = await jsonFetch<{ candidates: Candidate[] }>('/api/image-gen/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            run_id: runId,
            kind: viewKind,
            item_id: item.id,
            prompt: item.draftPrompt,
            references: item.selectedReferences.map((ref) => ref.path),
            candidate_count: candidateCount,
          }),
        });
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
              <Box>
                <Typography variant="h6">{selectedRun?.name || '画像候補の比較と採用'}</Typography>
                <Stack direction="row" spacing={0.75} alignItems="center" className="breadcrumb">
                  <Typography variant="caption">{breadcrumb}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {visibleItems.length}件
                  </Typography>
                </Stack>
              </Box>
            </Stack>
            <Tooltip title="出力フォルダを再読み込み">
              <IconButton onClick={() => window.location.reload()} color="primary" aria-label="出力フォルダを再読み込み">
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </AppBar>

          <GlassPanel variant="frosted" density="comfortable" slot="controls" className="controls glassControls">
            <GlassSurface variant="solid" density="compact" slot="controls" className="controlStation runStation">
              <Typography variant="caption" className="stationLabel">出力先</Typography>
              <FormControl fullWidth size="small">
                <InputLabel>出力先</InputLabel>
                <Select value={runId} label="出力先" onChange={(event) => setRunId(event.target.value)}>
                  {runs.map((run) => (
                    <MenuItem key={run.id} value={run.id}>
                      {run.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </GlassSurface>

            <GlassSurface variant="solid" density="compact" slot="controls" className="controlStation targetStation">
              <Typography variant="caption" className="stationLabel">対象</Typography>
              <Tabs value={viewKind} onChange={(_, value) => setViewKind(value)} className="tabs">
                <Tab value="asset" label="素材" />
                <Tab value="scene" label="シーン" />
              </Tabs>

              {viewKind === 'asset' && (
                <Tabs value={assetFilter} onChange={(_, value) => setAssetFilter(value)} className="tabs assetSubTabs">
                  <Tab value="chara" label="キャラ" />
                  <Tab value="obj" label="小物" />
                  <Tab value="asset" label="全素材" />
                </Tabs>
              )}
            </GlassSurface>

            <GlassSurface variant="solid" density="compact" slot="controls" className="controlStation countPanel">
              <Typography variant="caption" className="stationLabel">生成枚数</Typography>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography fontWeight={800}>同時生成枚数</Typography>
                <Chip color="primary" label={`${candidateCount}候補`} />
              </Stack>
              <Slider
                min={2}
                max={16}
                step={1}
                value={candidateCount}
                onChange={(_, value) => setCandidateCount(value as number)}
                marks={[
                  { value: 2, label: '2' },
                  { value: 8, label: '8' },
                  { value: 16, label: '16' },
                ]}
              />
            </GlassSurface>
          </GlassPanel>

          {busy && <LinearProgress />}
          <Box className="gridScroll">
            <Box className="promptGrid">
              {!busy && !items.length && (
                <GlassPanel variant="frosted" density="spacious" className="emptyGallery">
                  <Typography fontWeight={900}>展示室が空です</Typography>
                  <Typography variant="body2" color="text.secondary">
                    出力先と素材 / シーンを選び、素材内ではキャラ / 小物 / 全素材を切り替えてください。
                  </Typography>
                </GlassPanel>
              )}
              {!busy && Boolean(items.length) && !visibleItems.length && (
                <GlassPanel variant="frosted" density="spacious" className="emptyGallery">
                  <Typography fontWeight={900}>このカテゴリは空です</Typography>
                  <Typography variant="body2" color="text.secondary">
                    asset 側は chara / obj / asset の順に整理されています。別カテゴリへ切り替えてください。
                  </Typography>
                </GlassPanel>
              )}
              {visibleItems.map((item) => (
                <Card
                  key={item.id}
                  className={`promptCard ${item.generating ? 'is-generating' : ''}`}
                  variant="outlined"
                  onFocus={() => setActiveItemId(item.id)}
                  onMouseEnter={() => setActiveItemId(item.id)}
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
                        onChange={(event) => patchItem(item.id, { draftPrompt: event.target.value })}
                      />

                      <Autocomplete
                        multiple
                        options={references}
                        value={item.selectedReferences}
                        getOptionLabel={(option) => option.label}
                        isOptionEqualToValue={(a, b) => a.path === b.path}
                        onChange={(_, value) => patchItem(item.id, { selectedReferences: value })}
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
                          item.selectedReferences.map((ref) => (
                            <Box key={ref.path} className="referenceThumb">
                              <img src={fileUrl(runId, ref.path)} alt={ref.label} loading="lazy" decoding="async" />
                              <Typography variant="caption" noWrap>{ref.label}</Typography>
                              <IconButton
                                size="small"
                                aria-label={`${ref.label}を参照から外す`}
                                onClick={() =>
                                  patchItem(item.id, {
                                    selectedReferences: item.selectedReferences.filter((selected) => selected.path !== ref.path),
                                  })
                                }
                              >
                                ×
                              </IconButton>
                            </Box>
                          ))
                        ) : (
                          <Typography variant="caption" color="text.secondary">参照画像なし</Typography>
                        )}
                      </Box>

                      <Button
                        variant="contained"
                        startIcon={<AutoAwesomeIcon />}
                        disabled={item.generating || !item.draftPrompt.trim()}
                        onClick={() => generateItem(item)}
                      >
                        画像生成
                      </Button>
                      </Stack>

                      <Box className="comparisonWall">
                        {item.generating && <LinearProgress className="cardProgress" />}
                        <Box className="comparisonHeader">
                          <Typography fontWeight={900}>候補比較</Typography>
                          <Chip size="small" label={item.generating ? '生成中' : item.candidates.length ? '確認待ち' : '未生成'} />
                        </Box>
                        <Box className="candidateGrid">
                        {item.existingImage && (
                          <GlassStatusRim variant="solid" density="compact" slot="candidate" status="idle" className="candidate existing">
                            <Box className="candidateMedia">
                              <img src={fileUrl(runId, item.existingImage)} alt="現在の画像" loading="lazy" decoding="async" />
                            </Box>
                            <Typography variant="caption" className="candidateLabel">現在</Typography>
                          </GlassStatusRim>
                        )}
                        {candidateSlots(item, candidateCount).map((candidate) => (
                          (() => {
                            const isSelected = item.selectedCandidatePath === candidate.path;
                            const isAdopted = Boolean(candidate.path && adoptedKeys.has(`${runId}:${candidate.path}`));
                            const isPlaceholder = !candidate.path && !candidate.error;
                            const selectCandidate = () => {
                              if (candidate.path) {
                                setActiveItemId(item.id);
                                patchItem(item.id, { selectedCandidatePath: candidate.path });
                              }
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
                            aria-label={candidate.path ? `候補${candidate.index}を選択` : undefined}
                            className={`candidate ${isPlaceholder ? 'placeholderCandidate' : ''} ${isAdopted ? 'is-adopted' : ''}`}
                            onClick={selectCandidate}
                            onKeyDown={(event) => {
                              if ((event.key === 'Enter' || event.key === ' ') && candidate.path) {
                                event.preventDefault();
                                selectCandidate();
                              }
                            }}
                          >
                            <Box className="candidateMedia">
                              {candidate.path ? (
                                <img src={fileUrl(runId, candidate.path)} alt={`候補${candidate.index}`} loading="lazy" decoding="async" />
                              ) : (
                                <Typography className="candidateMessage">
                                  {candidate.error || (item.generating ? '生成中' : '待機中')}
                                </Typography>
                              )}
                            </Box>
                            <Typography variant="caption" className="candidateLabel">
                              候補 {candidate.index}
                              {isAdopted ? ' / 採用済み' : isSelected ? ' / 採用候補' : ''}
                            </Typography>
                          </GlassStatusRim>
                            );
                          })()
                        ))}
                        </Box>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              ))}
            </Box>
          </Box>

          <GlassDock edge="bottom" variant="frosted" density="compact" slot="footer" className="bulkFooter">
            <Stack direction="row" spacing={1} alignItems="center" minWidth={0}>
              <Chip size="small" color={selectedForInsert.length ? 'primary' : 'default'} label={`${selectedForInsert.length}件採用候補`} />
              {bulkGenerating && <Chip size="small" color="primary" label={`生成中 ${bulkCompletedCount + bulkFailedCount}/${bulkTotal}`} />}
              {!bulkGenerating && bulkTotal > 0 && <Chip size="small" label={`生成完了 ${bulkCompletedCount + bulkFailedCount}/${bulkTotal}`} />}
              {bulkFailedCount > 0 && <Chip size="small" color="error" label={`失敗 ${bulkFailedCount}`} />}
              {insertStatus === 'running' && <Chip size="small" color="primary" label="挿入中" />}
              {insertStatus === 'success' && <Chip size="small" color="success" label={`${lastInsertedCount}件 挿入済み`} />}
              {insertStatus === 'error' && <Chip size="small" color="error" label="挿入失敗" />}
              {downloadError && <Chip size="small" color="error" label={downloadError} />}
              <Typography variant="caption" color="text.secondary" noWrap>
                {selectedRun?.path || '出力先未選択'}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" startIcon={<AutoAwesomeIcon />} onClick={generateBulk} disabled={!visibleItems.length || bulkGenerating}>
                一括生成
              </Button>
              <Button variant="outlined" startIcon={<DownloadIcon />} onClick={downloadZip}>
                一括ダウンロード
              </Button>
              <Button className="insertAction" variant="contained" startIcon={<SaveAltIcon />} onClick={insertBulk} disabled={!selectedForInsert.length || insertBusy}>
                リポジトリへ挿入
              </Button>
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
