# Run Index Numbering

- run dir 直下に `p000_index.md` を置き、人が最初に見る入口にできること
- `100` 番台ごとに大工程を割り当て、`10` 番台刻みは既定値を持ちつつ stage ごとに柔軟に再定義できること
- `p000_index.md` で current stage / next required human review / stage table / current run inventory を見られること
- md だけでなく、audio / image / video / logs / scratch を含む全成果物を stage と role に分類できること
- narration は `p400` の本文正本と `p800` の音声生成を分けて扱えること
- 第1段階では `assets/**`, `logs/**`, `scratch/**` の物理 rename を行わず、navigation layer として番号を導入すること
