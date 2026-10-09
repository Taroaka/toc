# Design

新規 downstream repair module に stage別診断adapter、閉じた差分schema、厳密適用、永続RepairSessionループを置く。
共通decoderのreceipt付き入口を使う。コード修復後も残る構文エラーは、p200の共通syntax-only patchを適用可能な場合だけ呼ぶ。対象外は候補を記録して停止し、生成指示を再送しない。
p330/p420は初回だけ全文生成。以後は保存済み候補に限定patchを適用する。
意味エラーは診断されたcutを許可範囲にする。診断不能な集約エラーは全体再生成へ拡大せず停止する。
本番runやサーバーは変更せず、fake providerとtmp_pathで検証する。

追補: p200に合わせてAPI schemaへunit ID/base digestとpath別native値型を固定。未登録asset IDだけ削除可能とし、元index基準で検証、末尾から削除する。
