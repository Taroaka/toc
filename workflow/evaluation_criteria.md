# Evaluation Criteria

ToC の評価は prompt 単体の出来ではなく、pipeline の各 stage が
「必要構造・必要根拠・必要 gate」を満たしているかで判定する。

## 目的

- `research -> story -> script -> manifest -> video` を共通の評価面に揃える
- exact text 一致ではなく、構造・根拠・運用 gate の通過可能性を評価する
- `eval_report.json` と `run_report.md` を毎 run の標準成果物にする

## 評価対象

### 1. Research

- sources 数
- canonical story dump / legacy synopsis の有無
- chronological events / legacy beat sheet の量
- source passages / facts / handoff_to_story の有無
- conflicts の棚卸し
- confidence score
- scene_plan / scene_id は任意参考であり research 合否条件にしない

### 2. Story

- 2–4 candidate の比較
- chosen candidate と rationale
- scripted scene の research refs
- hybridization 承認要否の明示

### 3. Script

- scene / cut の最小構造
- 実質的な内容量
- `TODO` / `TBD` の残存有無

### 4. Manifest

- renderable scene / cut の存在
- `1 cut = 1 narration`
- narration text field の存在
- cut duration 上限
- `character_ids` / `object_ids` の明示
- immersive の invariant（experience / no on-screen text）

### 5. Video

- `video.mp4` existence
- render status
- human review 用の `run_report.md`
- narration list / media duration の最低整合

## 判定方式

- deterministic check:
  - file exists
  - YAML parse
  - field exists
  - count threshold
  - path exists
- rubric check:
  - TODO 未解消
  - coverage
  - rationale の有無
  - gate の未解決状態

各 stage score は `passed_checks / total_checks` とする。

## 出力

`eval_report.json` の最小形:

```json
{
  "generated_at": "ISO8601",
  "run_dir": "output/<topic>_<timestamp>",
  "flow": "toc-run|scene-series|immersive",
  "profile": "fast|standard",
  "overall": {
    "passed": true,
    "score": 0.84,
    "failed_stages": []
  },
  "stages": {
    "research": {
      "passed": true,
      "score": 0.88,
      "checks": []
    }
  }
}
```

`run_report.md` は上記から生成し、手書きしない。

## 運用

- fast:
  - pointer/state/schema/tests 向け
  - 存在確認と最小構造を優先
- standard:
  - final review 前提
  - TODO 禁止、gate 未解決禁止、manifest/video 契約をより厳しく見る

## 回帰セット

- `workflow/evals/golden-topics.yaml`
