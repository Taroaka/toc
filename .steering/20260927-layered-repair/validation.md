# 検証

- broader regression: 128 passed（research/visual/p400含む共通decoder回帰、story/selection/CLI/patch）。
- field helperとpipeline: 18 passed（不正leaf削除追加後）。
- syntax runtime: 37 focused/runtime tests（担当agent）。
- 実run ledgerのattempt 3/6/7は末尾の余分な } 1文字のみの修復でdecode成功。run自体は変更していない。
- 正常な旧scene cacheはprompt/schema/model/payload hashが一致すれば再利用され、provider再呼び出し0件。
- field patch API schemaを直接送るCLIテスト、JSON構文エラーで元author taskを再送しないテスト、正常項目不変、指定外path拒否、非収束時に全文再生成へ拡大しないテストを実施。
- 実際のgpt-6-luna / ToC app-server / ChatGPT認証 / read-only temp cwdでstrict patch schemaを直接送信。返却patchがapply_field_patchに通り、1つの人物IDだけ変更、未指定項目不変を確認。
  schema SHA-256: d6ed90c73888c151645d9817ba2ec095d004c46bbd55fa94006be627e0e51815
- 独立レビュー対応: envelope不正をinner syntax修復に通さない、syntax rule/modelをcacheに結び付ける、field補正非収束で正常な文章へ拡大しない。
- pointer validator、diff whitespace、Python構文確認成功。
- 稼働中run・サーバー・予算は変更していない。後続stageのfield補正展開は別スレッド用handoffへ記載。
