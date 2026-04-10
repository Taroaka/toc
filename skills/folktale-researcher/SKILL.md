---
name: folktale-researcher
description: |
  Research folklore, myth, or legend topics for a country or region and turn them into a candidate slate or a Story-first ToC skeleton with source and sensitivity notes.
  Use when: the user asks for folktales, myths, legends, regional story ideas, or culturally aware source research for a specific country or region.
---

# Folktale Researcher（国別 物語ネタ調査）

## Overview

国/地域の民話・神話・伝承を「動画制作に使えるネタ」として整理し、必要なら ToC の調査テンプレ（`workflow/research-template.yaml`）へ落とし込む。
モデル内知識だけで断定せず、曖昧さと検証TODOを明示する。

## When to Use

- 「◯◯国（地域）の有名な物語を知りたい」「この国の昔話で動画にできるネタを出して」
- 日本以外の文化圏で、英雄譚/怪異/教訓/起源譚などのストーリー候補が必要
- 1本選んで、後続の story/script/manifest に繋がる **Story-first の骨格**を作りたい

## Instructions

### 0) Clarify（最初に確認）

最低限この3点を確認し、未指定なら仮定して進める（仮定は明示）:

- 対象: 国/地域（例: “Scotland”, “Polynesia”, “West Africa (Yoruba中心)”）
- 用途: ネタ出しのみ / 1本深掘りして research yaml まで
- 制約: 対象年齢、怖さ、宗教/民族表現の配慮、実写/アニメ、尺（例: 10〜20分想定）

### 1) Idea slate（候補を8〜12本）

候補は「文化圏の代表性」と「映像化しやすさ」の両方で選ぶ。各候補に以下を付ける:

- Title（英名/現地名/日本語訳があれば） + 1行要約
- Core motifs（3〜6語）: 例）underworld descent / trickster / taboo / transformation
- Why it works（制作向け推しポイント）: 視覚的ギミック、セットピース、感情カーブ
- Variants（地域差・バリエーションの有無）: あるなら1〜2行
- Sensitivity notes（配慮）: 聖典/宗教儀礼/植民地主義的な扱いの回避など
- Rights note（権利注意）: “folkloreの骨格は古いが、近代作家の再話は著作物” になり得る…等
- Confidence（high/medium/low）: 自信度を正直に

### 2) Pick one（1本選択）

ユーザーが未選択なら、目的に合う上位1〜3本を推薦し、理由を短く述べて選んでもらう。

### 3) Deep dive（Story-first で骨格を確定）

選ばれた1本について、まず「そもそもどんな話か」を確定する（裏話より先）:

- canonical synopsis（one_liner / short_summary / beat_sheet 10〜20）
- characters（protagonist / key_allies / key_antagonists / core_goal / stakes / setting）
- hero_story_validation（fit と根拠。弱いビートがあるなら補強案も）

### 4) Scene mapping（scene_id に配賦）

`docs/information-gathering.md` の方針に従い、**最低20シーン**の骨格を埋める。
ここでは「情報の置き場」を決めるのが目的なので、各 scene は 1〜2行でよい。

### 5) Sources & verification（出典と検証TODO）

このスキルは“調べ方”も成果物に含める。
Webアクセスできない環境でも、最低限「当たるべき典拠の候補」を列挙する:

- encyclopedia（例: Britannica / national library / museum）
- academic（論文・民俗学の概説・注釈版）
- primary-ish（叙事詩の翻訳版、採集民話集、神話集の原典系）

そして、誤りやすい点（固有名詞・地域差・年代・宗教的扱い）に検証TODOを付ける。

## Output Format

### A) Idea slate（Markdown推奨）

見出し例:

- Region / constraints
- Candidate stories（8〜12）
- Recommendation（1〜3）
- What to verify next（箇条書き）

### B) Deep dive（YAML: `workflow/research-template.yaml` 互換）

可能なら `workflow/research-template.yaml` を満たす YAML を出力する（キーは崩さない）。
`metadata.sources_used` は、URLが出せない場合は「出典名/書名/機関名」でも可。

## Examples

### Prompt example（ネタ出し）

> 「アイルランドの昔話で、没入型ライド向きのネタを10個出して。怖すぎないやつ」

### Prompt example（深掘り）

> 「候補の中から “The Children of Lir” を選ぶ。ToCの `workflow/research-template.yaml` で出して」

## Guidelines（重要）

- 断定しない: あいまいな点は “未検証” と書く
- 文化配慮: 神聖視される物語や儀礼を“ネタ消費”しない。表現上の注意点を先に出す
- 剽窃回避: 近代作家の文章をなぞらない。骨格（プロット）を自分の言葉で要約する
- 権利注意: 「昔話そのもの」と「近代の再話/翻案」は区別して扱う（最終判断は人間）
