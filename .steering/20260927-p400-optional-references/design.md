# 設計

- reveal info IDs/new reveal elementsは任意の許可配列。invalid leafのみallow_removeを付け、minimum_remaining_items=0を明示する。
- patch適用は既存値がまだinvalidであること、許可されたpathであることを確認し、元indexの降順で削除する。正常な要素、文章、カメラ、cut identityを保持。
- その他のID配列は従来のminimum=1を保ち、候補が空かつ空配列不可ならprovider開始前に停止する。
- resolved asset registryの復元は、形状診断がすべてasset参照の場合に限定せず、一つでもasset参照がありasset request自体が有効なら実施する。他の診断は引き続き残す。
- patch schema/prompt準備を予算予約より前に行う。
- first_frame_briefに内部scene参照が混ざる等でcompilerがcurrent_moment_missingを返す場合、そのフィールドだけsemantic補正に戻す。compilerのチェックは緩めない。
- server/UI terminal状態の修正は別担当が行う。親は関連API/フロントファイルを同時編集しない。
