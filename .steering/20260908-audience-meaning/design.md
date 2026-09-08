# 設計

- docs/story-creation.md に汎用指針の正本を置く。観客の理解の始点、根拠となる体験、
  終点（維持・深化・不確かさを含む）を既存欄の prose として扱う。
- 反復要素は物体に限定せず、行為、関係、構図、音、状況も扱う。反復や意味変更を
  採用しない作品にも追加義務を作らない。
- 世界観を掘る問いは選択用とし、宗教性や神秘性、単一の共同体観を要求しない。
- story / visual_value テンプレートには既存欄を使うコメントを追加する。
  script / asset / adaptation / affect 文書には短い接続指示を置く。
- 上流で決めた意味・開示順を下流が具体的な行動、視覚・音の証拠へ翻訳する。
  抽象的な意図を provider prompt へ直接入れない。
- キャンベルの思想と ToC 独自の応用を区別し、原典・財団解説・ヴォグラーへの参照を残す。

自動作成の prompt は `toc/story_authoring.py` の共通 instruction を使い、
`toc/story_author_pipeline.py` の single / batch / repair に同じ指示を渡す。
stage readset の文書パス登録だけで自動生成へ反映済みとは扱わない。

frontend の cut 化では、authored `audience_knowledge_delta` を物理的な
`immediate_consequence` や汎用の理解文で上書きしない。event obligation と選択済み primary
beat からの投影で authored 値を優先し、空値の旧 artifact は既存の補完動作を保つ。
scene intent 全体の再設計や reveal model の変更はこの差分に含めない。

既存の未コミット変更は保持する。開始時に削除されていた workflow/script-template.yaml は
別作業によって再作成されたため、本変更では触らず、現在の記述先の確認にのみ利用する。
新規 runtime 契約を作らないため、独立した計画成果物や必須チェック項目も増やさない。
