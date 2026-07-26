# p500 resume skill requirements

## Goal

フロント作成済みの ToC run に問題が見つかって Codex で前半成果物を修正した後、別 run を新規作成せず、同じ run を p500 から再生成できるようにする。

## Success criteria

- `research.md`、`story.md`、`visual_value.md`、`script.md`、`video_manifest.md` と p400 以前の状態を保持する。
- p500 以降の request、semantic review、生成 media、render 成果物を後続処理から見えない状態へ退避する。
- 退避前に dry-run で対象を確認でき、apply 後も checkpoint から旧成果物を監査できる。
- 同じ run に対する frontend create/resume と同時実行しない。
- p400 readiness が再評価で approved にならない run は p500 へ進めない。
- reset 後は同じ run directory の p500 から p650 または p680 まで再実行できる。

## Out of scope

- p400 より前の research/story/script を自動で書き直すこと
- 別 run の削除や統合
- semantic QA gate の弱体化
- 退避済み checkpoint の自動復元 UI
