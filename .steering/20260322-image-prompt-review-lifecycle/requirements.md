# Requirements

## Goal

画像生成前の prompt collection review を repo-wide の契約として明文化し、各 entry が subagent review 結果、false 理由、修正後の再判定、人間 override を明示できるようにする。

## Requirements

- 対象は特定作品ではなく repo 全体の image prompt review lifecycle とする
- prompt collection の各 entry は subagent review の真偽を明示する
- subagent が false を付けた場合は reason key を 1 つ以上残す
- false reason は修正対象の種類が分かる短い key で扱う
- 修正は prompt collection / manifest 側へ反映してから再 review する運用を正本化する
- 修正が解消したら subagent は同じ entry を true に戻せることを明記する
- 人間 override は「false を true に上書きする」意味ではなく、「finding を理解して例外許容した」ことを記録する契約にする
- docs とテンプレートは runtime 実装の有無に依存しない形で、最低限の field と semantics を示す
