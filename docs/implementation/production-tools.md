# 制作補助ツール

画像・動画の確認画面にある折りたたみ式の「制作補助ツール」パネルから使う、任意のローカル処理をまとめる。既存の候補を比較し、メモを残し、画像の部分状態差分や動画編集候補を作り、ショット配置を概略表示する。新しいAI画像・動画生成、canonicalな原稿の書き換え、全sceneへの自動反映は行わない。

## 使い方と保存物

API prefixは `/api/image-gen/production-tools`。GETに `run_id`、`item_id`、`kind=image|video` を渡して現在の素材、hash、request revision、候補、メモ、配置案を読む。POST操作は以下。

| suffix | 用途 |
| --- | --- |
| `/notes` | 候補に問題・試す変更・結果と、残す/見送る/保留の人の所感を追記 |
| `/variant` | 画像の基準画像、編集画像、正規化矩形範囲、状態説明から画像派生物を作成 |
| `/video-edit` | currentな動画候補をtrim・色調整・fadeして動画派生物を作成 |
| `/select-video` | currentな動画候補を明示的に選択 |
| `/geometry` | ショット配置案を保存 |

候補メモの正本はrun直下の `candidate_notes.json`（`candidate_notes_v1`）。各追記は候補path、候補bytesのSHA-256、request revisionに結び付き、全体revisionの一致を要求する。元候補のbytesが変わるか削除されるとメモはstaleとして表示される。記録は助言用の人の観察であり、候補の自動採用・棄却や画像/動画生成を起動しない。

空間配置のプレビュー案はrun直下の `spatial_previews.json`（`spatial_previews_v1`）に保存する。配置schema `shot_geometry_v1` はメートル単位のZ-up座標、camera、allowed asset IDを持つ。未知のassetや未知フィールドは拒否する。表示は `shot_geometry_projection_v1` をSVGへ投影した上面図とカメラ視点の概略であり、Blender等の3Dレンダー、照度・光量の物理シミュレーションではない。p400で執筆された `execution.geometry` は、後続の画像/動画promptへ同じ配置の目安として投影される。UIで保存した案はplanning-onlyであり、保存だけではp400を書き換えない。source revisionが変わればstale表示となり、実制作への反映にはcanonicalなsource編集と明示的な再構築が必要。隠れたprompt overrideとして使わない。

画像の部分状態差分は `assets/test/state_variants/<item_id>/<uuid>.png` と同名JSON receiptへ保存する。基準画像と編集画像は同じ表示寸法で、両方の送信SHA-256が現在bytesと一致する必要がある。最大32個の正規化矩形範囲について、基準画像を土台に指定範囲の画素だけを編集画像からコピーし、範囲外の基準画素を保つ。元画像は変更しない。UIから派生画像を参照として追加する操作は明示的に行う。参照追加はAI生成を呼ばない。

動画編集は `assets/test/video_edits/<item_id>/<uuid>.mp4` と同名JSON receipt（`video_edit_receipt_v1`）を作る。start/durationによるtrim、brightness、contrast、saturation、gamma、fade in/outを設定できる。元動画・元音声を保持し、音声streamがある場合は同じ時間窓を切り出してfadeを適用する。音声の元の開始offsetを保ち、窓に音声が重ならない場合は無音streamを作って同期を維持する。receiptはsource/output bytes hash、request revision、設定、実測尺とstream情報を結び、派生編集のsource chainも検証する。

動画候補を選択する操作は既存候補の選択を明示的に上書きする。選択候補は現在のrequest revision、bytes hash、編集receiptと一致しなければならない。さらに現在のplanned cut durationとナレーションの最小尺の大きい方を満たす必要がある。短い編集結果はプレビュー・書き出しには使えても採用できず、尺を黙ってretimeしない。採用変更は `production_selections.json` に記録し、p860音響承認を再確認待ちにする。選択後に動画bytesが変わる、またはrequestが変わると選択は無効になる。

## 共通の状態・制約

素材pathはrun内の通常ファイルに限定され、SHA-256を操作時に再照合する。動画編集receipt、候補、画像variantは不変の派生物として扱う。API request modelは未知フィールドを拒否し、geometryも未知キーを拒否する。revision競合や古い候補を無言で採用しない。候補を選んだ事実は人の選択としてstateへ記録されるが、他sceneやpromptへ自動伝播しない。

実装: `server/production_tools_api.py`、`toc/spatial_previs.py`、`toc/asset_variants.py`、`toc/candidate_notes.py`、`toc/video_editing.py`、`server/web/src/ProductionToolsPanel.tsx`。

## 関連仕様

- [Cinematic language and observable execution](cinematic-language.md)
- [Asset Bibles](asset-bibles.md)
- [p860 BGM・SE](sound-design.md)
- [Video generation](../video-generation.md)
