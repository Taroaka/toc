# 作業

- [x] Adobe / BFI / StudioBinderの解説を調査
- [x] 人物なしsubの設計書を作成
- [x] 正本・readsetへ接続
- [x] YAML、リンク、pointer docs、差分を確認（validate-pointer-docs、readsetの存在・重複確認、git diff --check）

## 新規作成・生成フェーズ実装

- [x] 新規visual authorの境界判断を構造化し、欠落・不正sourceを拒否
- [x] p420で人物なしsubをmaterializeし、scene尺・coverage・前後接続へ反映
- [x] 画像／動画compilerの人物禁止と、人物参照の混入防止
- [x] subを独立した動画生成単位として保持
- [x] author指定の無音を人間確認と偽らず扱う
- [x] source beat文字列IDを数値IDとして拒否していた構造検証を修正
- [x] 関連9テストファイル: 156 passed, 142 subtests passed。最終動画制約調整後の対象2ファイル: 73 passed, 117 subtests passed。provider課金呼出しなし
- [x] コードレビュー指摘を修正: shared contractのhandoff二重更新、人物向け動画定型文、明示的人物動作の混入。1/2subのscript/manifest一致と人物定型文除外を回帰テスト
