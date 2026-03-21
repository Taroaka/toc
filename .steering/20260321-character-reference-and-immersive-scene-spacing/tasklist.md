# Tasklist: character reference と immersive scene spacing

## 1) 仕様化

- [ ] `docs/implementation/image-prompting.md` の `character_reference` 説明を full-body only に更新する
- [ ] `workflow/immersive-ride-video-manifest-template.md` か関連テンプレに、参照識別子の記載方法を追加する
- [ ] immersive story の scene numbering guidance を 10-step spacing 推奨へ更新する

## 2) 互換性整理

- [ ] 既存の `scene_id` 連番運用を禁止しない旨を明記する
- [ ] manifest 順を正とする後段処理方針があれば、その互換条件を確認する
- [ ] 既存の reference / character assets に numeric scene_id 依存の説明が残っていないか確認する

## 3) 命名と運用

- [ ] readable reference identifier の命名例を複数追加する
- [ ] `character_reference` scene のレビュー観点に「全身が写っていること」を追加する
- [ ] immersion 系の playbook / template で 10-step spacing の例を示す

## 4) 受け入れ基準

- [ ] character reference scene を見て、後からキャラ外観を再現しやすいことが分かる
- [ ] 人間が参照 ID を読んで用途を判別できる
- [ ] 旧来の scene_id 運用からの移行が、破壊的変更ではなく推奨変更として読める
