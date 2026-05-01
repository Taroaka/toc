# YouTube チャンネル運用とポリシー

最終更新: 2026-04-26
用途: 新規チャンネル立ち上げ時に外してはいけない設定と運用上の注意点をまとめる。

---

## 1. 最初に固めるべき運用判断

- audience setting をどうするか
- AI / synthetic disclosure の境界をどう運用するか
- 誰にどの権限を渡すか
- コメント初期設定をどうするか
- upload defaults をどこまで使うか

---

## 2. Audience setting

### 原則

`made for kids` か `not made for kids` かは、見た目ではなく `実際の対象視聴者` で決める。

にわかのAI の想定では、通常は `not made for kids` が基本。
理由:

- 民話・神話・伝承を扱っていても、チャンネルの主目的は児童向け番組ではない
- AIエージェント制作や全自動生成の裏側公開も含むため、一般の物語・映像・技術チャンネルに近い

### 誤設定の影響

`made for kids` にすると、コメントや通知、メンバーシップなど多くの機能が制限される。
迷って雑に kids 判定を入れない。

---

## 3. AI / synthetic disclosure

### 原則

現実と誤認されうる altered / synthetic content は disclosure 対象。

### にわかのAI での考え方

- script 作成補助
- thumbnail 補助
- caption 補助
- 一般的な制作支援

これだけなら、通常は disclosure の中心論点ではない。

一方で、

- 本物の映像や現実の出来事に見える synthetic scene
- 現実人物の face / voice swap
- 実在の出来事を本物らしく捏造した見せ方

こうしたケースは disclosure 対象になりうる。

### 実務ルール

- `AIを使った` ことと `disclosure が必要` なことは同じではない
- にわかのAI はブランド説明では AI 使用を明示してよい
- ただし formal disclosure は、現実誤認リスクのあるケースに絞る

---

## 4. 権限設計

### 原則

- shared password で回さない
- channel permissions を使う
- 最小権限で始める

### 実務ルール

- 複数人で触る可能性があるなら Brand Account 前提に寄せる
- upload / publish / comment moderation を誰が持つかを分ける
- permission は YouTube の全 surface を完全にカバーしない前提で考える

---

## 5. コメント設定

### launch 前に決めること

- blocked words
- link を含むコメントの扱い
- hold for review の基準
- custom channel guidelines を使うか

### 注意

- custom channel guidelines は案内であって自動執行ではない
- moderation の基準は、後からではなく最初に置く

---

## 6. Upload defaults と公開設定

### upload defaults

毎回同じ項目は defaults に寄せてよい。

例:

- 説明欄の共通部分
- 基本タグ
- visibility 前の既定値

### 注意

- desktop での upload defaults は mobile upload や editor にそのまま効かない
- device 差を前提に、最後は目視確認する

### schedule

- 公開日時の見え方には時差の注意がある
- date 表示を意識するなら、意図した日付で publish されるよう合わせる

---

## 7. feature access

初期設定で確認する。

- custom thumbnails が使えるか
- advanced features が必要な項目がないか
- verification や phone check が必要か

新規チャンネルで詰まりやすいのは、`機能がある前提で運用を設計すること`。
使えることを確認してからチェックリスト化する。

---

## 8. にわかのAI の推奨運用デフォルト

- audience: `not made for kids`
- AI disclosure: `現実誤認リスクのあるものだけ厳密対応`
- permissions: `shared password なし / least privilege`
- comments: `review 前提の初期設定`
- uploads: `desktop defaults を使うが最終目視は必須`

---

## 9. 次に読むもの

- ブランドと初期設定 → `channel-branding-and-setup.md`
- launch 導線設計 → `channel-launch-packaging.md`
- 公開前の実務 → `upload-checklist.md`
