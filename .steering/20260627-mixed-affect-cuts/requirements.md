# Requirements: Mixed Affect Cut Design

## Goal

ToC の p420 cut 設計に、混合的感情、緊張と解放、余韻の設計を optional な判断レイヤーとして組み込む。

## Success Criteria

- すべての cut に必須化せず、必要と判断した cut だけが `mixed_affect_design` を持てる。
- 採用した場合は、視覚、音声、音/リズム、handoff のどこで支えるかを明示できる。
- 既存の `1 cut = 1 intent`、scene_event grounding、reveal boundary、first-frame / motion / narration 分離を壊さない。
- frontend create scaffold が作る `cut_contract` にも optional field が入り、空運用にならない。
- 既存未コミット変更を巻き戻さない。

## Scope

- `docs/affect-design.md`
- `docs/data-contracts.md`
- `docs/implementation/cut-loop.md`
- `docs/script-creation.md`
- `workflow/*cut*template*`
- `workflow/*video-manifest-template.md`
- `scripts/toc-immersive-frontend-run.py`

## Non-Goals

- 全 cut へ混合感情を強制しない。
- 実視聴者の `experienced emotion` を artifact に逆流させない。
- 興行最適化や高 arousal 連打を品質基準にしない。
