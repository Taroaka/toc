# Audio Duration Padding Requirements

この内容は恒久仕様として `docs/implementation/video-integration.md` に昇華する。
本ファイルは作業単位の履歴として保持する。

## 要求

- 音声実秒に対して、映像尺をどう決めるかを明文化する
- `音声秒 = 映像秒` ではなく、前後の余白を持たせる運用を標準化する
- メインカット / サブカット / 余韻重視カットで、余白量の目安を示す
- 既存の `main 5–15秒 / sub 3–15秒` ルールと矛盾しない形にする
