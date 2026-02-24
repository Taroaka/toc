# ToC Agent Guide

このファイルは複数モデルのAIエージェントに対してのドキュメントとするため、 **`AGENTS.md` と `CLAUDE.md` で同一内容**として管理する（差分を作らない）。

## リポジトリの個性（北極星）

1) **AIエージェントが開発を進める**前提で、進め方（要求→設計→タスク）をドキュメント化している  
2) **物語トピック→動画生成**を Claude Code の **slash command** から簡単に実行できる（想定）

## 起動（Claude Code slash command）

- 起点:
  - `/toc-run`（標準フロー）
  - `/toc-scene-series`（sceneごとのQ&A動画を複数本生成）
  - `/toc-immersive-ride`（没入型：First-person POV 実写ライド体験の単発動画）
- 使い方（想定）:
  - `/toc-run "topic" [--dry-run] [--config <path>]`
  - `/toc-scene-series "topic" [--dry-run] [--min-seconds 30] [--max-seconds 60] [--scene-ids 1,2,3]`
  - `/toc-immersive-ride --topic "topic" [--stage video|script] [--config <path>]`
- コマンド説明:
  - `.claude/commands/toc/toc-run.md`
  - `.claude/commands/toc/toc-scene-series.md`
  - `.claude/commands/toc/toc-immersive-ride.md`
- 実行手順（全体）: `docs/how-to-run.md`

## まず参照するドキュメント（プロンプト別）

あなた（エージェント）への指示が「台本の本作成」ではなく「ネタ収集（調査）」寄りのとき、次に読むべき正本は以下。

- **ネタ収集 / 調査 / リサーチ**: `docs/information-gathering.md`
  - 実行担当エージェント: `.claude/agents/deep-researcher.md`
  - 出力テンプレ: `workflow/research-template.yaml` / `workflow/research-template.production.yaml`
- **調査→物語化（story.md）**: `docs/story-creation.md`
  - 実行担当エージェント: `.claude/agents/director.md`
  - 出力テンプレ: `workflow/story-template.yaml`
- **sceneごとの根拠（evidence.md）**: `.claude/agents/scene-evidence-researcher.md`
- **台本（script.md）/ manifest（video_manifest.md）作成**:
  - 没入型（/toc-immersive-ride）: `.claude/agents/immersive-scriptwriter.md`
  - scene-series: `.claude/agents/scene-scriptwriter.md`
  - テンプレ/契約: `workflow/video-manifest-template.md`（+ `docs/implementation/` 配下）

## `improve_claude_code/` の位置づけ

- `improve_claude_code/` は ToC 本体とは別の「開発運用レイヤー」（multi-agent実行基盤）として同居している
- ToC本体（`/toc-run` などの動画生成フロー）は `toc` / `scripts` / `docs` を中心に単体で実行可能
- 並列AI実行や command pack / hooks / skills を使うときに `improve_claude_code/` を利用する
- 連携時は `scripts/ai/multiagent.sh` を入口にし、`queue` / `dashboard.md` / `instructions` / `memory` をシンボリックリンクで project root に見せる

## state 管理（ファイル）

state は **コード内の状態ではなく**、プロジェクトフォルダの **テキスト**で管理する。

- 置き場所: `output/<topic>_<timestamp>/state.txt`
- 形式: key=value（簡易テキスト）
- 更新方式: **追記型**
  - ブロック区切りは `---`
  - 最新ブロックが現在状態
- 再開: 最新ブロックを読み込んで続きから進める
- 擬似ロールバック: 過去ブロックをコピーし、必要なキーを変更して末尾に追記
- スキーマ: `workflow/state-schema.txt`

## ドキュメント構成（どこに何があるか）

- 恒久仕様: `docs/`（入口は `docs/README.md`）
- 実装に直結する正本: `docs/implementation/`（`.steering` から昇華した仕様）
- 作業単位の履歴: `.steering/`（`requirements.md` → `design.md` → `tasklist.md`）
- テンプレ/契約: `workflow/`（`workflow/*-template.yaml`, `workflow/state-schema.txt`）
- 実行支援: `scripts/`
- 設定: `config/`（例: `config/system.yaml`）
- Claude Code: `.claude/commands/`（/toc-run など）
- 生成物: `output/`（原則 gitignore 対象）

## 進め方（spec-first）

- 変更が非自明なら `.steering/YYYYMMDD-<title>/` を作り、
  `requirements.md` → `design.md` → `tasklist.md` の順で固める（必要なら各段階で承認を取る）
- 実装は **設計に沿って最小変更**で行う（依頼されたこと以外はしない）
- 変更後は可能な範囲で検証（例: `python -m compileall .`、CI想定のdry-runなど）

## 会話時の報告（作業完了時）

- 編集したファイルごとに「何をどう変えたか」を丁寧に伝える（要点→補足の順）
- そのファイルの置き場所（ディレクトリ）がこの構造で妥当な理由を、`docs/` / `.steering/` / `workflow/` などの役割と照らして説明する
- もし妥当でない/迷う場合は、代替案（置き場所候補）と、今回移動しない判断理由も書く
- 可能なら、実行した検証コマンドと結果も添える
- 文章は機械的な箇条書きだけでなく、短い会話調の説明（「今回は〜なので〜に置きました」）を混ぜて読みやすくする

## Secrets / env

- `.env.example` を `.env` にコピーして利用
- シークレットは絶対にコミットしない

---

## ALWAYS START WITH THESE COMMANDS FOR COMMON TASKS

**Task: "List/summarize all files and directories"**

```bash
fd . -t f           # Lists ALL files recursively (FASTEST)
# OR
rg --files          # Lists files (respects .gitignore)
```

**Task: "Search for content in files"**

```bash
rg "search_term"    # Search everywhere (FASTEST)
```

**Task: "Find files by name"**

```bash
fd "filename"       # Find by name pattern (FASTEST)
```

### Directory/File Exploration

```bash
# FIRST CHOICE - List all files/dirs recursively:
fd . -t f           # All files (fastest)
fd . -t d           # All directories
rg --files          # All files (respects .gitignore)

# For current directory only:
ls -la              # OK for single directory view
```

### BANNED - Never Use These Slow Tools

* ❌ `tree` - NOT INSTALLED, use `fd` instead
* ❌ `find` - use `fd` or `rg --files`
* ❌ `grep` or `grep -r` - use `rg` instead
* ❌ `ls -R` - use `rg --files` or `fd`
* ❌ `cat file | grep` - use `rg pattern file`

### Use These Faster Tools Instead

```bash
# ripgrep (rg) - content search
rg "search_term"                # Search in all files
rg -i "case_insensitive"        # Case-insensitive
rg "pattern" -t py              # Only Python files
rg "pattern" -g "*.md"          # Only Markdown
rg -n "pattern"                 # Show line numbers
rg -A 3 -B 3 "error"            # Context lines

# ripgrep (rg) - file listing
rg --files                      # List files (respects .gitignore)
rg --files | rg "pattern"       # Find files by name

# fd - file finding
fd -e md                        # All .md files

# jq - JSON processing
jq . data.json                  # Pretty-print
```

### Search Strategy

1. Start broad, then narrow: `rg "partial" | rg "specific"`
2. Filter by type early: `rg -t python "def function_name"`
3. Batch patterns: `rg "(pattern1|pattern2|pattern3)"`
4. Limit scope: `rg "pattern" src/`

### INSTANT DECISION TREE

```
User asks to "list/show/summarize/explore files"?
  → USE: fd . -t f  (fastest, shows all files)
  → OR: rg --files  (respects .gitignore)

User asks to "search/grep/find text content"?
  → USE: rg "pattern"  (NOT grep!)

User asks to "find file/directory by name"?
  → USE: fd "name"  (NOT find!)

User asks for "directory structure/tree"?
  → USE: fd . -t d  (directories) + fd . -t f  (files)
  → NEVER: tree (not installed!)

Need just current directory?
  → USE: ls -la  (OK for single dir)
```
