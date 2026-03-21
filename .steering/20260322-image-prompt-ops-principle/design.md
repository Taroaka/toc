# Design: Image Prompt Ops Principle

## Approach
各正本に同じ主張を重複なく短く入れる。

1. `docs/implementation/image-prompting.md`
   - 画像 prompting の冒頭に「正解は構造化・anchor・reference 固定・レビュー」という原則を明記する
   - prompt collection が review artifact であることを強調する

2. `docs/how-to-run.md`
   - 画像生成手順の例に prompt collection の確認を明示する
   - 直接 manifest から画像生成に入らないことを補足する

3. `workflow/playbooks/image-generation/reference-consistent-batch.md`
   - 画像 batch の手順として、prompt collection をレビューしてから生成することを再強調する
   - anchor/reference を先に固定する手順であることを明示する

## Non-goals
- 画像 prompt の完全再設計
- runtime の生成アルゴリズム変更
- 既存の prompt collection ファイルの個別編集
