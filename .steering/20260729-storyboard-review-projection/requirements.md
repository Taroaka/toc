# Requirements

## Goal

`scene_storyboard` の p680 後処理が追加する `scenes[].render_units` を
p800 由来の実行 overlay として扱い、承認済みの pre-p800 review evidence
を不必要に stale にせず、安全に storyboard 成果物を確定する。

## Success criteria

- `scenes[].render_units` だけの追加・更新では、列挙された pre-p800
  review-loop / semantic-review source digest は変わらない。
- `cut_id`、duration、prompt、asset その他の manifest 変更、および
  narration / video-motion / video-review の manifest 変更は evidence を
  stale にする。
- malformed manifest は projection 時に fail closed する。
- YAML alias で scene 外にも到達できる field は除外せず、complete fence と
  unclosed fence が混在する manifest も fail closed する。
- policy marker がない旧 evidence は exact raw bytes 一致時だけ互換扱いし、
  canonical p500 resume で新 projection policy へ安全に再 freeze できる。
- storyboard materializer は `render_units` 以外の manifest 正本を変更せず、
  projection drift を transaction 内で検知して rollback する。
- fresh create、image-only resume、canonical p500 resume は同じ p680
  storyboard finalizer を使う。
- p500 subprocess が materialization の canonical owner で、server parent
  は subprocess 完了後の validation だけを行う。

## Scope

- `toc/` の review-source projection helper
- `toc/review_loop.py`
- `toc/semantic_review.py`
- `scripts/build-semantic-review-pack.py`
- `scripts/review-image-prompt-story-consistency.py`
- `server/image_gen_app.py`
- `scripts/resume-from-p500.py`
- focused tests
