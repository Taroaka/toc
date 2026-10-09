# p420: 原作に根拠のある未登録素材の受け渡し

ユーザー承認済み。既存のscene単位p400 LLM呼出しにasset_requestsを追加する。
対象は設計したcutが使う人物・物・場所だけ。原作全体の網羅登録や、根拠のない創作素材は対象外。

- authorは不足素材名、種類、sourceのcanonical entity pointer、引用付き使用根拠、使用cutを返す。
- cutはrequest:<request_id>を仮参照できる。コードが原作pointer・引用一致・使用cutを検証し、安定したasset IDへ解決する。
- 同じsource identityは重複作成しない。既存素材の再利用はexisting_asset_idで明示する。名前だけで別物を同一視しない。
- base registryと拡張registry、解決記録を保存。保存後もsourceから再計算して照合する。
- manifestのasset bibleへ追加し、実際のcut使用からp500 inventory/plan/requestへ渡す。
- 根拠がない/引用違い/未使用/重複IDは既存の構造修正ループへ返す。新しいLLM工程やcriticは追加しない。
- 既存directionでasset_requestsがないものは旧契約のまま読める。

検証: request解決・重複再利用・不正source・同名別物・場面の根拠・script/manifestとp500の使用対応・保存後の改変検出。

## 実装上の決定

- 新規参照の自由な外観説明は今回の登録処理で使わず、sourceに一致する対象名をp500へ渡す。既存素材の外観は変更しない。
- 同名の既存候補がある場合、既存IDの再利用か、別物とする対象IDと理由を明示する。
- 再利用でも引用をbible/planへ引き継ぐ。初期registryはsourceだけから算出し、解決後のrole bindingから自己変更しない。
- 後続beatの素材を先に使うことを防ぐ検査では、対象名を含む引用のbeat位置を使う。無関係な早い引用で許可を前倒しできない。

## 状態

実装・構造検証・p500リクエスト作成まで完了。[検証記録](validation.md)を参照。
実モデルでの列挙精度と実画像の生成品質は今回の自動テストの対象外。
