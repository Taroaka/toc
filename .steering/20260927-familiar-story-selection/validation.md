# 検証結果

- 回帰95件成功。採用版のみのArchitect/完成story/p400投影、別版省略、採用版内省略理由、単一版legacy互換性、既存resumeを確認。
- 独立レビューで指摘されたsource_basis型不正、null契約のlegacy化、別版の省略ID、矛盾する版所属を修正。
- 版別event_ids順を全版横断のresearch配列順より優先。未採用の資料は全件coverage対象にしない。
- 新しい選定契約では、summary/motifs/既定の主小道具も採用内容へ限定。全researchは保存する。
- pointer validatorとdiff whitespace検査成功。
- 作品固有の分岐・固定の版順位なし。知名度の判断は根拠と不確実性を示すLLMの選定として実装し、架空の人気統計は作らせない。
- 既存runの再開・改稿・画像生成は未実行。次回authoringのpromptが変わるため、旧Architectキャッシュは一致しない。

## 並行タスク：Codex CLI

担当subagentがHomebrew経路で0.153.4から0.157.1へ更新。
/opt/homebrew/bin/codex -> /opt/homebrew/Caskroom/codex/0.157.1/bin/codex。
ToCと同じChatGPT認証・app-server経路でgpt-6-astraとgpt-6-lunaのread-only no-op turnがともにcompleted。旧Lunaの400は再現しない。モデル設定変更・run再開・サーバー再起動なし。
