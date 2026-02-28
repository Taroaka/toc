# /toc-run

ToC（TikTok Story Creator）をトピックから実行するためのコマンド。

## 使い方（想定）

```
/toc-run "桃太郎" --dry-run
```

## 期待される出力

- `output/<topic>_<timestamp>/` が作成される
- `state.txt`（追記型）が生成される
- カット設計は **1カット=1ナレーション** を基本に、メイン(5–15秒) + 必要ならサブ(3–15秒)で進める（詳細は `docs/implementation/video-integration.md`）

詳細は `docs/how-to-run.md` を参照。
