# 調査・設計確認 — 2026-10-13

今回は設計資料だけを作成。本体コード、作品、モデル設定、API課金状態を変更していない。

## 読み取り確認

| 確認箇所 | 現状と今回の扱い |
|---|---|
| `.steering/20261010-intent-to-shot-design/decision.md` / `implementation-validation.md` | 別の赤ペンでshot設計・一覧・新規/選択cutへの適用を決定済み。実装記録があるため、重複実装を計画しない。記載のテスト件数を今回再実行した結果とは扱わない |
| `toc/p400_authoring.py:614,665` | 初稿へshot_planとSHOT_AUTHOR_GUIDANCEを渡している |
| `server/cut_direction_api.py:231,392,417` | 現在のauthorは単一cut・テキスト中心。隣接cutを読むが、実画像pixelsは渡さない |
| `server/codex_app_server.py:687` / `toc/story_author_runtime.py:352` | 下位run_turnはlocal_images対応。上位の構造化author wrapperには同引数がなく、拡張対象 |
| `server/cut_direction_api.py:664,830` | visual-only保護、投影、revision確認とrequest再作成を共有する土台 |
| `toc/shot_direction.py:44` / `toc/shot_timeline.py:69` | 親の有効尺とchild合計の検証を再利用 |
| `server/image_gen_app.py:8912` / `scripts/sync-manifest-durations-from-audio.py:286` | 音声実尺の親尺同期はあるが、shot_planの自動再配分はない |
| `scripts/toc-immersive-frontend-run.py:3` | 画像工程p650/p680まで。全編の音声・動画生成をそのまま自動完走するrunnerとは扱わない |
| `server/image_gen_app.py:17203,17785` | p830 request作成とp840動画生成の入口。準備operationをこの前へ接続する設計 |
| `toc/media_resume.py:67` | 既存のoperation journal・input/output hash再利用を使う |
| `toc/production_repair.py:62` | 回数予算のledger。金額上限の保証として流用しない |

行番号は調査時点。実装着手時は関数名と現在の差分を再確認する。

## 独立確認

文脈を分離したLunaの限定読み取り調査を実施し、本文の接続点・実画像添付・音声尺とshot_planの差を反映した。詳細設計の読み取りレビューで、既存moduleをそのまま使えない3点が判明し、追加実装の責務として本文とタスクへ反映した。

1. MediaJournalはrun全体hashに束縛される。既存の再開保護は維持し、入力変更後は新operationへrequest/bytes検証付きで既存候補を引き継ぐ設計とした。
2. 全providerで受理IDの即時永続化が保証されているわけではない。対象adapterに送信前intent、受理ID保存、unknown時の再POST禁止を明示した。
3. 既存cut editorはrun全体の同時変更を拒否する。既存checkを緩めず、pureな投影/検証のみ共有し、新scene commitに依存照合と差分適用を実装する設計とした。

資料内の相対リンク検証に成功。`python scripts/validate-pointer-docs.py` は `Pointer docs valid.`。設計レビューは実装の安全性や実映像の品質を検証したものではない。

## 実施しない検証

本体未変更なので製品の全テストやbuildは実施しない。有料のauthor/画像/音声/動画生成、シンデレラの変更、別物語の制作は開始しない。文書リンクとpointerガイドの整合だけを確認する。
