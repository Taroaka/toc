# Requirements

## Goal

`narration` と `visual_beat` の距離を、固定ルールではなく scene の役割と作品の結末型に応じて判断する設計へ更新する。

## Requirements

1. opening / middle / ending の単純3分割だけでなく、scene の没入維持フェーズか意味付与フェーズかを区別できる
2. 序盤・中盤は原則として `narration` と `visual_beat` を近づけ、没入を阻害しない
3. 終盤は「必ず離す」のではなく、まだ没入維持が必要なら近づけてもよい
4. 映像のあとに意味が残る一文を許可・推奨する条件を定義する
5. 作品ごとの結末型（happy / bittersweet / tragic / cautionary など）を考慮できる
6. 浦島太郎のような代償型の物語では、「何を失ったのか」「なぜそれが重いのか」を終盤ナレーションの重要評価軸に含める
