import React, { useEffect, useMemo, useState } from 'react';
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
import DownloadIcon from '@mui/icons-material/Download';
import ImageIcon from '@mui/icons-material/Image';
import SendIcon from '@mui/icons-material/Send';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import RefreshIcon from '@mui/icons-material/Refresh';
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

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0e1113',
      paper: '#171b1f',
    },
    primary: {
      main: '#d7ff4f',
    },
    secondary: {
      main: '#82d8ff',
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

function App() {
  const [runs, setRuns] = useState<RunFolder[]>([]);
  const [runId, setRunId] = useState('');
  const [kind, setKind] = useState<'asset' | 'scene'>('asset');
  const [candidateCount, setCandidateCount] = useState(2);
  const [items, setItems] = useState<EditableItem[]>([]);
  const [references, setReferences] = useState<ReferenceOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string }>>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const selectedRun = runs.find((run) => run.id === runId);

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
      `/api/image-gen/requests?run_id=${encodeURIComponent(runId)}&kind=${kind}`,
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
  }, [runId, kind]);

  const selectedForInsert = useMemo(
    () => items.filter((item) => item.selectedCandidatePath && item.output),
    [items],
  );

  const patchItem = (itemId: string, patch: Partial<EditableItem>) => {
    setItems((prev) => prev.map((item) => (item.id === itemId ? { ...item, ...patch } : item)));
  };

  const generateItem = async (item: EditableItem) => {
    if (!runId) return;
    patchItem(item.id, { generating: true, candidates: [] });
    try {
      const data = await jsonFetch<{ candidates: Candidate[] }>('/api/image-gen/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: runId,
          kind,
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
      patchItem(item.id, { candidates: [{ index: 1, status: 'failed', path: null, error: String(error) }] });
    } finally {
      patchItem(item.id, { generating: false });
    }
  };

  const generateBulk = async () => {
    if (!runId) return;
    setItems((prev) => prev.map((item) => ({ ...item, generating: true, candidates: [] })));
    try {
      const data = await jsonFetch<{ results: Array<{ itemId: string; candidates: Candidate[] }> }>(
        '/api/image-gen/generate-bulk',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            run_id: runId,
            kind,
            concurrency: Math.min(candidateCount, 4),
            items: items.map((item) => ({
              run_id: runId,
              kind,
              item_id: item.id,
              prompt: item.draftPrompt,
              references: item.selectedReferences.map((ref) => ref.path),
              candidate_count: candidateCount,
            })),
          }),
        },
      );
      const byId = new Map(data.results.map((result) => [result.itemId, result.candidates]));
      setItems((prev) =>
        prev.map((item) => {
          const candidates = byId.get(item.id) ?? [];
          return {
            ...item,
            generating: false,
            candidates,
            selectedCandidatePath: candidates.find((candidate) => candidate.path)?.path ?? null,
          };
        }),
      );
    } catch (error) {
      setItems((prev) =>
        prev.map((item) => ({
          ...item,
          generating: false,
          candidates: [{ index: 1, status: 'failed', path: null, error: String(error) }],
        })),
      );
    }
  };

  const downloadZip = async () => {
    if (!runId) return;
    const paths = items.flatMap((item) => item.candidates.map((candidate) => candidate.path).filter(Boolean)) as string[];
    const response = await fetch('/api/image-gen/download-zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, paths }),
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'image-gen-candidates.zip';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const insertBulk = async () => {
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
  };

  const sendChat = async () => {
    if (!chatInput.trim()) return;
    const message = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { role: 'user', text: message }]);
    setChatBusy(true);
    try {
      const data = await jsonFetch<{ message: string; approvals: unknown[] }>('/api/chat/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, run_id: runId || null, session_id: 'image_gen_chat' }),
      });
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', text: data.message || (data.approvals.length ? '承認が必要です。' : '応答がありません。') },
      ]);
    } catch (error) {
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
          <AppBar position="static" color="transparent" elevation={0} className="topbar">
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Avatar variant="rounded" className="mark">
                <ImageIcon />
              </Avatar>
              <Box>
                <Typography variant="h6">ToC Image Gen</Typography>
                <Typography variant="caption" color="text.secondary">
                  prompt matrix / reference routing / Codex image candidates
                </Typography>
              </Box>
            </Stack>
            <Tooltip title="Reload output folders">
              <IconButton onClick={() => window.location.reload()} color="primary">
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </AppBar>

          <Stack className="controls" spacing={2}>
            <FormControl fullWidth size="small">
              <InputLabel>output folder</InputLabel>
              <Select value={runId} label="output folder" onChange={(event) => setRunId(event.target.value)}>
                {runs.map((run) => (
                  <MenuItem key={run.id} value={run.id}>
                    {run.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Tabs value={kind} onChange={(_, value) => setKind(value)} className="tabs">
              <Tab value="asset" label="asset" />
              <Tab value="scene" label="scene" />
            </Tabs>

            <Box className="countPanel">
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography fontWeight={800}>同時生成枚数</Typography>
                <Chip color="primary" label={`${candidateCount} candidates`} />
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
            </Box>
          </Stack>

          {busy && <LinearProgress />}
          <Box className="gridScroll">
            <Box className="promptGrid">
              {items.map((item) => (
                <Card key={item.id} className="promptCard" variant="outlined">
                  <CardContent>
                    <Stack spacing={1.5}>
                      <Stack direction="row" justifyContent="space-between" gap={1}>
                        <Box minWidth={0}>
                          <Typography fontWeight={900} noWrap>
                            {item.id}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" noWrap>
                            {item.output || 'no output path'}
                          </Typography>
                        </Box>
                        <Chip size="small" label={item.executionLane} color={item.executionLane === 'bootstrap_builtin' ? 'secondary' : 'default'} />
                      </Stack>

                      <TextField
                        label="プロンプト"
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
                            <img src={fileUrl(runId, option.path)} alt="" />
                            <span>{option.label}</span>
                          </Box>
                        )}
                        renderInput={(params) => <TextField {...params} label="参照画像" placeholder="何枚でも選択" />}
                      />

                      <Button
                        variant="contained"
                        startIcon={<AutoAwesomeIcon />}
                        disabled={item.generating || !item.draftPrompt.trim()}
                        onClick={() => generateItem(item)}
                      >
                        画像生成
                      </Button>

                      {item.generating && <LinearProgress />}
                      <Box className="candidateGrid">
                        {item.existingImage && (
                          <Box className="candidate existing">
                            <img src={fileUrl(runId, item.existingImage)} alt="existing" />
                            <Typography variant="caption">current</Typography>
                          </Box>
                        )}
                        {item.candidates.map((candidate) => (
                          <Box
                            key={`${item.id}-${candidate.index}`}
                            className={`candidate ${item.selectedCandidatePath === candidate.path ? 'selected' : ''}`}
                            onClick={() => candidate.path && patchItem(item.id, { selectedCandidatePath: candidate.path })}
                          >
                            {candidate.path ? <img src={fileUrl(runId, candidate.path)} alt={`candidate ${candidate.index}`} /> : <Typography>{candidate.error}</Typography>}
                            <Typography variant="caption">candidate {candidate.index}</Typography>
                          </Box>
                        ))}
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              ))}
            </Box>
          </Box>

          <Box className="bulkFooter">
            <Typography variant="caption" color="text.secondary" noWrap>
              {selectedRun?.path || 'output folder未選択'}
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" startIcon={<AutoAwesomeIcon />} onClick={generateBulk} disabled={!items.length}>
                一括生成
              </Button>
              <Button variant="outlined" startIcon={<DownloadIcon />} onClick={downloadZip}>
                一括ダウンロード
              </Button>
              <Button variant="outlined" startIcon={<SaveAltIcon />} onClick={insertBulk} disabled={!selectedForInsert.length}>
                一括repo内挿入
              </Button>
            </Stack>
          </Box>
        </Box>

        <Box className="chatPane">
          <Stack direction="row" alignItems="center" spacing={1} className="chatHead">
            <Avatar variant="rounded" className="chatMark">
              <ArchiveIcon />
            </Avatar>
            <Box>
              <Typography fontWeight={900}>Codex App Chat</Typography>
              <Typography variant="caption" color="text.secondary">
                prompt design / file edits / approvals
              </Typography>
            </Box>
          </Stack>
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
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void sendChat();
                }
              }}
            />
            <IconButton color="primary" onClick={sendChat} disabled={chatBusy}>
              <SendIcon />
            </IconButton>
          </Stack>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

