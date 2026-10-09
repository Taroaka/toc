# 設計

- docs/implementation/b-roll-design.mdを制作ルールと技法集の正本にする。
- 一般的な映画技法の説明とToC固有の制約を区別し、出典を記載する。
- script-creation.mdから参照し、script / manifest / narration / scene_implementation / video_generationのrequired_docsに登録する。
- cut_role: sub、既存viewer / cinematic / first-frame / motion / asset / handoff項目で指示する。未知の必須フィールドや検証器は追加しない。
- 境界の前後を一組で判断し、同じ空間導入の重複や必須情報のsubへの追い出しを避ける。
- 音の先行・残響接続は編集設計として記録する。現行renderでの自動対応を保証しない。

## 実装追補

新規authorのみboundary_b_roll_v1を要求し、各sceneのboundary_b_roll（reason/cuts）を検証する。旧v2入力は保持。scene末尾の既存event状態を参照するBロールを専用materializerで追加し、人物中心の既存main scaffoldを通さない。scene総尺を全cutへ配分、coverage・handoff・selectorへ反映する。compilerはsubの人物禁止を明示し、人物参照付きsubは拒否する。
