# 直近1か月のスキル見直し

## 結果

利用を確認した26種類を評価し、カスタムスキル14種類を更新した。同名の既存正本・配布先33ディレクトリへ同期済み。更新した74文書はMarkdownとスキルUI用YAMLのみ（リポジトリ内49文書、個人用配布先25文書）。

14種類の `SKILL.md` 合計は **3,770行 → 338行（約91%減）**。これは入口の行数で、参照資料を含む全体量や実際のtoken数ではない。フロント/バックエンドのコード例は内容を維持して用途別参照へ移した。

## 判断基準と期間

- 2026-08-15 00:00 JST〜今回の依頼開始（2026-09-15）。今回自身の読み込みは除外。
- Codex履歴DBと期間内更新の1,245タスクのrolloutを照合。カタログ掲載・更新日・作成/同期/監査目的だけの閲覧は実使用と数えない。
- これはアクセス可能なローカル履歴に基づく対象選定。クラウドや他端末の履歴を網羅した利用統計ではない。
- [OpenAIの記事](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)に従い、発動条件、必要時の資料読込、固定手順、判断境界、完了条件を評価。既存のユーザー判断や実装上の不変条件は保持。
- 使用証跡は [usage-evidence.json](usage-evidence.json)。各スキルの代表的な読み込みイベントの日時・ログ・行を記録し、会話本文は複製していない。

## 更新した14種類

| スキル | 入口の行数 | 変更 |
| --- | ---: | --- |
| `backend-patterns` | 587 → 18 | API・データ・運用の3参照へ分割。Node系の設計判断に発動を限定。 |
| `coding-standards` | 520 → 19 | 汎用入門例と固定レイアウトを削除し、既存規約と具体的な保守性判断に限定。 |
| `frontend-patterns` | 631 → 16 | 部品/状態・描画性能・操作性の3参照へ分割。計測対象のない最適化を促さない。 |
| `goal-forge` | 176 → 36 | 未決事項だけを質問。既決条件の再承認、旧モデル/巨大context/無制限権限の必須化を解除。 |
| `hero-journey-cinematic-setpieces` | 39 → 16 | 道具・舞台装置設計に用途を限定。現行schemaへ委譲し、設計だけの依頼と生成を区別。 |
| `improve-workflow` | 45 → 20 | 計画のみ/実装完遂を区別。全体テスト・ツール導入・並列起動を自動化しない。 |
| `marketing-skills-router` | 67 → 22 | チャネル別の入口へ整理。価格・人数・商品規則の重複を正本参照へ置換。 |
| `review-subagent-fix-loop` | 117 → 24 | レビューのみ/修正依頼を区別。サブエージェントの適用方針を守り、UI promptも整合。 |
| `security-review` | 494 → 23 | 変更した信頼境界に適用範囲を限定。無関係な全項目チェックやサービス固有の必須設定を除去。 |
| `tdd-workflow` | 422 → 22 | 80%一律・全テスト層・固定時間制約を削除。既存coverage規則とToC固有不変条件を保持。 |
| `toc-immersive-runner` | 201 → 35 | 新規生成/状態確認/再開を分岐。完了契約は必要時の参照へ分離。 |
| `toc-resume-p500` | 230 → 38 | POSTが再開実行であることを明記しCLI二重起動を防止。p500詳細は分離、lock/hash/来歴を保持。 |
| `toc-server-restart` | 116 → 34 | 確認だけならhealth check。再起動時は既存helperを使用し、結果を不必要に再検証しない。 |
| `verification-loop` | 125 → 15 | 固定の全工程と15分タイマーを削除。変更・失敗・未解決リスクに応じて検証。 |

## 評価し、変更しなかった12種類

| 対象 | 判定 |
| --- | --- |
| `toc-research`, `toc-scene-design`, `toc-image-prompt`, `toc-narration`, `toc-video-gen` | 各12行で、工程と正本を特定する短い入口になっている。必須readsetと検証契約は意味があるため維持。 |
| `.system/skill-creator` | 記事に沿う現行ガイド。用途とリスクに応じた具体性・資料分離を既に指示している。 |
| `.system/openai-docs` | 公式資料と用途別参照のルーティングを維持。システム配布の現行版を直接改変しない。 |
| `.system/imagegen` | 長いdescriptionと重複する固定手順は改善候補。組込みツールの詳細に依存するシステム配布物のためキャッシュを改変せず、提供元更新で扱う。 |
| Sales `index`, `build-business-case` | 説明の広さとmandatory deck offer等は改善候補。履歴の1.1.1と現在の1.1.0-alpha.2が異なり、提供元管理のため直接改変しない。 |
| `frontless_review`, `control-in-app-browser` | 使用証跡はあるが当時のSKILL.mdが現在存在しない。旧工程・旧プラグインを復活させない。 |

## 対象から除外した10種類

`toc-p500-bootstrap-image-runner`, `toc-p600-image-runner`, `toc-no-reference-image-runner`, `codex-parallel-image-batch`, `folktale-researcher`, `era-explainer`, `selfhelp-trend-researcher`, `vertical-shorts-creator`, `youtube-studio-upload`, `seo-rank-watch`。期間内に見つかった記録はスキルの作成・更新・契約整理・同期・監査目的で、実行ワークフローとしての利用を確認できなかった。その他の未使用スキルも変更していない。

## 検証と変更の保存

- 14種類すべてで skill-creator の `quick_validate.py` 成功。Markdown相対リンクの実在、metadataの保持、例示コードの分離元との一致を確認。
- 判断例の手動確認は [validation.md](validation.md)。独立モデルによるフォワードテストや実API実行は行っていない。
- `python scripts/validate-pointer-docs.py` 成功。AGENTS.md/CLAUDE.md/root-pointer-guide.mdは今回変更していない。
- shared skillの既存テストは変更前に4件中3件成功、1件失敗。対象外 `seo-rank-watch` に文字列 `Use when:` を要求する既存テストが原因。対象外スキルやテストを変更して通すことはしていない。
- [changes.patch](changes.patch) は既存変更を含む作業開始時点との差分。元の全対象は `/tmp/astra-skills-20260915/backup` に保存。適用は全元ファイルのhash一致を確認してから行う。
- 実行コード・モデル設定・権限設定・生成結果・公開状態は変更しない。

## 適用後の確認

- 33ディレクトリすべての `quick_validate.py` が成功。74文書が検証済み改訂案とhash一致。
- 対象ディレクトリ内のそれ以外の既存ファイルは、作業開始時のhashと一致。
- 今回のリポジトリ変更に対する `git diff --check` 成功。
- pointer validatorは再度成功。shared skill testsは変更前後とも3成功・1既存失敗で、新規の失敗はない。
- 未使用のスキル、配布元管理キャッシュ、既存のアプリ実装・設定・生成成果物は今回の適用リストに含めていない。
