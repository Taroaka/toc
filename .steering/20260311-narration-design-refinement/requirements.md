# Narration Design Refinement Requirements

この内容は恒久仕様として `docs/implementation/video-integration.md` と
`.claude/agents/narration-writer.md` に昇華する。
本ファイルは作業単位の履歴として保持する。

## 要求

- ナレーションを「映像の言い換え」ではなく「映像に無い重要情報を足す層」として定義する
- Narration Writer が判断しやすいように、何をナレーションで運び、何を映像へ残すかを明文化する
- 1カット=1ナレーション運用を維持したまま、各行の情報価値を上げる品質基準を追加する
- 映画的/没入型と、昔話/伝承系で、ナレーションの強さの目安を持てるようにする
