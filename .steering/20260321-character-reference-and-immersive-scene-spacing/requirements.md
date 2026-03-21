# Requirements: character reference と immersive scene numbering の整備

## 背景 / 問題

- `character_reference` scene は、参照画像としての役割が強い一方で、body framing の制約が曖昧だと上半身中心や部分切り出しが混ざりやすい。
- 参照用 scene は機械的に並ぶだけだと、人間が後から見て「どの参照か」を取り違えやすい。
- immersive story 系の scene numbering は、後から scene を差し込みたい運用と相性が悪い場合があり、10-step spacing を推奨したい。
- ただし、既存の scene_id ベースの資産・テンプレ・後段処理との互換性は壊したくない。

## ゴール

- `character_reference` scene は **full-body only** とし、全身が見える参照画像として統一する。
- `character_reference` scene には、人間が読める参照識別子を付ける。
- immersive story の scene numbering guidance を **10-step spacing 推奨** に移しつつ、既存の連番運用と後方互換を維持する。

## 非ゴール / 除外

- 既存のすべての scene_id を一括で振り直すこと
- 参照画像生成モデルやレンダラの再設計
- `character_reference` 以外の通常 scene の構図ルールを大きく変更すること
- 互換性を壊す形でのテンプレ全面改訂

## 成功指標

- `character_reference` の定義に「full-body only」が明記される
- 参照識別子の命名規則が明文化され、運用で読める形になる
- immersive story の scene numbering guidance が 10-step spacing を推奨しつつ、既存資産の利用方法が明確になる
- 既存の scene_id 参照・manifest 順依存の運用を壊さない方針が明記される
