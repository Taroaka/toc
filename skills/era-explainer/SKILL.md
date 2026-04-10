---
name: era-explainer
description: |
  Turn an era, civilization, or culture topic into a ToC-ready explainer structure, from idea slate through research and scene planning, defaulting to cloud_island_walk.
  Use when: the user asks for a history explainer, civilization overview, culture video concept, or a way to present era knowledge as a guided visual experience instead of a text-heavy lecture.
---

# Era Explainer（ネタ収集その4: 時代解説）

## Overview

時代解説（例: 縄文時代）を “生成動画に向く体験” に変換する。
デフォルトは `cloud_island_walk`（雲上の島を散策しながら理解が深まる）で、**ゾーン=論点**として設計する。

## When to Use

- 「縄文時代を解説する動画を作りたい」
- 時代/文明/文化を “物語じゃなくても面白く” 見せたい

## Clarify

- 対象: 時代 + 地域（例: “縄文（日本列島）”, “古代ローマ”, “中世ヨーロッパ”）
- 対象者: 初学者 / 受験 / 大人向け
- トーン: ロマン/中立/反論も扱う
- フォーマット: `cloud_island_walk`（default） or `ride_action_boat`
- 尺: 60秒 / 10分 / 20分

## Output（slate）

同じ時代でも “切り口” を変えると面白くなる。以下を8〜12個出す:

- 切り口タイトル（例: 「縄文の食は“安定”だった？」）
- 1行要約（何を分かるようにするか）
- 見せ方（物理メタファ案）: 門/橋/器具/庭園…など
- 未検証ポイント（論争点/地域差/年代）
- 参照すべき典拠候補（博物館/図書館/概説書/論文）

## Deep dive（1本）

### 1) Story-first（骨）

解説でも “ストーリーの骨” が必要。
主人公は「視聴者（POV）」でよい。

- canonical synopsis（理解の変化を物語として書く）
- beat_sheet（理解が進む順序 10〜20）
- stakes（誤解が解ける/視点が変わる 等）

### 2) Scene plan（cloud walk推奨）

ゾーン=論点で設計し、scene_id 1..20 を最低限埋める。
各sceneは「理解が1つ前進する」こと。

### 3) 検証TODO（必須）

時代解説は不確実性が多い。以下を必ず出す:
- 年代幅（地域差/編年）
- 証拠の種類（遺物/遺構/文献/推定）
- 異説の有無（主流/少数説）

## Jomon example（要点だけ）

- Zones（例）:
  1) Arrival: どこまでが“縄文”か（年代の門）
  2) Foundation: 暮らし（住/食/道具）
  3) Tension: 地域差と気候変動、人口
  4) Synthesis: 信仰/土器/交易のネットワーク
  5) Return: 弥生移行と“断絶/連続”

## Guidelines

- 断定しない（“未検証/推定” のラベルを付ける）
- 文化/民族の扱いを雑にしない（単線進化史観に注意）
- 文字テロップで説明しない前提（cloud_island_walk の制約に合わせる）
