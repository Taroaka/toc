# p500 resume skill design

## Boundary

p500 resume は rollback ではない。`state.txt` の履歴を改変せず、新しい snapshot で p500 以降を pending/stale にし、旧成果物を `logs/resume/p500/<checkpoint>/artifacts/` へ移す pseudo rollback とする。

## Preserved inputs

- `research.md`
- `story.md`
- `visual_value.md`
- `script.md`
- `video_manifest.md`
- p400 以前の review/grounding artifact
- append-only `state.txt`

`video_manifest.md` は frontend create が p450 時点で production execution 枠まで materialize するため、phase 名だけで p600 所有と判定して退避しない。実在 media、request snapshot、downstream review/state を無効化して再 materialize する。

## Reset transaction

1. run directory が repository の `output/` 直下にあり symlink でないことを確認する。
2. 必須 upstream artifact と、旧 review artifact を除く fresh deterministic p400 readiness を確認する。
3. `dry-run` で downstream artifact 一覧と upstream digest を出す。
4. apply 時は `.locks/create_resume.lock` を non-blocking で取得する。
5. downstream artifact を checkpoint 配下へ移す。失敗時は移動済み artifact を元へ戻す。
6. append-only state に p500 以降の invalidation と resume marker を追加し、run index/status を再構築する。
7. p400 review artifact を再 materialize して完全な p400 readiness を通した後、p500 materialization、semantic QA、asset/image generation を既存 frontend runner の実装で同じ run に対して再実行する。

## Safety

- unknown artifact は自動退避しない。
- upstream canonical artifact は checkpoint 対象にしない。
- provider 実行は explicit apply 後だけ行う。
- 既存 create/resume lease が取得できない場合は fail closed にする。
