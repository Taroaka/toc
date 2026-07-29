# Design

## Review projection

`toc/review_projection.py` を唯一の projection / fingerprint 実装とする。
厳格に manifest YAML を読み、root mapping と `scenes` 構造を検証した後、
各 scene 直下の `render_units` だけを除外して canonical bytes と SHA-256
を作る。scene mapping は shallow detach してから除外し、YAML alias が
scene 外の同一 mapping を参照していても、その非 direct field は残す。
raw file hash と projected hash は同じ API から返す。

Projection は stage allowlist でのみ有効にする。

- review loop:
  `script`, `production_readiness`, `scene_set`, `scene_detail`,
  `cut_blueprint`, `asset`, `scene_implementation_hard`,
  `scene_implementation_judgment`
- semantic review:
  `scene_set`, `scene_detail`, `cut_blueprint`, `asset_plan`, `image_prompt`

その他と未知 stage は raw bytes に束縛する。

新しい review-loop snapshot / semantic scope の各 source digest record は
`fingerprint_policy` を持ち、input digest 自体にも policy を含める。
policy がない旧 v1 evidence は legacy raw-byte binding として、現在の
raw SHA-256 が完全一致するときだけ受理する。canonical p500 resume は
この旧 evidence を検証後、provider 実行前に新 policy で review evidence
を再 freeze する。したがって旧 raw evidence を overlay 変更後まで
暗黙に有効化しない。

pre-p680 の deterministic image-prompt story review が保存する
`manifest_sha256` も同じ projection SHA-256 とする。format v3 は
`manifest_fingerprint_policy` を必須にし、旧 v2 は exact raw bytes が
一致する間だけ互換扱いにする。server currentness は mtime ではなく
この digest binding だけで判定する。

## Storyboard finalization

共通 finalizer は次の順序を守る。

1. strict generic p680 validation
2. 既存 storyboard materialization が current なら再 materialize しない
3. review projection hash を保存
4. transactional storyboard materialization
5. projection unchanged を確認
6. specialized storyboard validation (`validate_base=False`)
7. strict generic p680 validation

Materializer は canonical `cut_id` と duration を補完・変更せず、missing /
invalid を拒否する。staging と canonical commit の双方で projection drift
を検出し、commit 後の drift は既存 transaction rollback を使う。

## Route ownership

- fresh create と image-only resume は共通 finalizer を呼ぶ。
- canonical p500 subprocess は image generation 後、apply lease 内で mode
  を再解決し、`scene_storyboard` の場合に共通 finalizer を呼んでから最終
  validation する。
- server の p500 parent worker は subprocess 後に validation だけを行う。
