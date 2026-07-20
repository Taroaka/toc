# Requirements

## Goal

動画 prompt を cut 設計書のキーやユーザー入力の単純連結ではなく、物語・scene・cut・参照フレームの正本から、動画 provider に必要な動きだけを投影して生成・レビューできる契約へ変更する。

## Success criteria

- 動画 prompt に影響する正本キーは、authoring relevance、provider projection、review visibility を registry で宣言する。
- provider prompt は、開始状態、主動作、カメラ、環境変化、感情変化、終了状態、連続性、追加禁止のうち active な group だけで構成する。
- `cut_contract`、event ID、target beat、設計 key 名、narration、画像 prompt 本文などの制作メタ情報を provider prompt へ出さない。
- Image-to-Video では、承認済み開始フレームから始まり、参照画像にない人物・重要物・reveal を追加しない。
- first/last frame 方式では、終了フレームを到達境界として扱い、フェード、カット、別ショット化を禁止する。
- Kling 系では、1 clip 1 intent、カメラ指示最大2つ、単一連続ショット、見た目の continuity を provider policy として適用する。
- request file、manifest payload、semantic review pack、実行時 prompt が同じ compiler output と hash を参照する。
- frontend の自由入力は authoring source として扱い、設計 contract と共に compile し、最終 provider prompt として無条件に保存しない。

## Scope

- video prompt projection registry / compiler
- batch request materialization と実行 prompt
- frontend video prompt materialization
- video motion semantic review pack
- manifest template / canonical docs / tests

## Out of scope

- 実際の動画 provider API 実行や課金
- 生成済み clip の視覚品質判定
- 過去 run の一括 migration
- cut / scene の物語設計そのものの再設計
