import { Box, Chip, Stack, Typography } from '@mui/material';

const labels: Record<string, string> = {
  'warm, calm narration, slow measured delivery': '温かく落ち着いた、ゆっくりした語り',
  'short pause': '短い間',
  'long pause': '長い間',
  calm: '落ち着いて',
  slowly: 'ゆっくり',
};

export function NarrationVoiceTags({ text, silent = false }: { text: string; silent?: boolean }) {
  if (silent) return null;
  const tags = [...new Set(Array.from(text.matchAll(/\[([^\[\]\r\n]+)\]/g), (match) => match[1].trim()).filter(Boolean))];
  return (
    <Box aria-label="語り方・間のタグ">
      <Typography variant="caption" color="text.secondary">語り方・間のタグ</Typography>
      <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mt: 0.5 }}>
        {tags.length ? tags.map((tag) => (
          <Chip key={tag} size="small" variant="outlined" title={`[${tag}]`} label={labels[tag.toLowerCase()] || tag} />
        )) : <Typography variant="caption" color="text.secondary">タグ未指定</Typography>}
      </Stack>
    </Box>
  );
}
