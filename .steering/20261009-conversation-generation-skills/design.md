# 設計

既存toc-video-genを更新し、toc-image-gen / toc-narration-gen / toc-bgm-gen / toc-se-genをskills/に追加する。共通の進捗確認手順はdocs/implementation/conversation-media-generation.mdに置き、各スキルからToCルート基準で読む。原稿用toc-narrationと画像prompt用toc-image-promptは所有範囲を保持する。実行は既存の共有runtime/validator/journalを使い、並行した生成プログラムは新設しない。

対象5スキルのみユーザーのCodexスキル領域へ登録する。既存ファイルは変更前に退避し、無関係なスキルは変更しない。スキル形式、参照パス、実際のfixtureに対する無課金の独立適用を確認する。
