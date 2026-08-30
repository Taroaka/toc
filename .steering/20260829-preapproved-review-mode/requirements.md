# Preapproved Review Mode Requirements

## Goal

Frontend create に明示的な「全レビュー済み」モードを追加し、外部レビューエージェントを呼ばずに通常の authoring・grounding・request materialization・画像生成を P680 まで継続する。

## Success Criteria

- 通常モードは既存どおり全レビューを実行する。
- `preapproved` モードは research/story/scene/cut/asset/image-prompt のレビューエージェントを呼ばない。
- 各 semantic review pack は現行 source digest に対して materialize され、review report は `preapproved` provenance を持つ合格 artifact として残る。
- 構造、入力digest、request snapshot、参照画像、生成画像の存在・provenanceなどの決定論的検証は省略しない。
- API request、CLI、create_input.json、state.txt にモードが保存される。
- frontend で通常 / 全レビュー済みを選択できる。
- P680 の最終画像レビューも承認済み状態として記録される。

## Scope

- `server/image_gen_app.py`
- `scripts/toc-immersive-frontend-run.py`
- `server/web/src/main.tsx`
- 関連 Python / frontend tests
- `docs/root-pointer-guide.md` の frontend create 例外契約

## Non-goals

- 生成物・画像が存在しない状態を成功扱いしない。
- path binding、schema、digest、provenance、provider output validation を迂回しない。
- 既存 run を無条件に後付け承認する API は追加しない。

