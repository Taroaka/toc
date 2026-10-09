# 検証結果

- 9 scenes / 61 cuts。既存58cutのaudio辞書とTTS継続文脈は追加前と一致。
- 保存済みsource artifactの実バイトを用いた構造preflightがpass。
- scene90は画像3枚、語り1cut、無音2cut。Jun / eleven_v4の候補生成に成功（4.754286秒）。新音声のユーザー合格判定は未実施。
- 語りの頭に0.5秒、cut尺8/6/7秒の静止画プレビューを作成。ffmpeg decode検証済み。動画生成モデル・BGMは未実行。
- フロントのナレーションpayloadに61cut、新音声候補が反映されることを確認。
- シーン8までのユーザー合格発言を保存。scene1は現行revisionに対応する音声候補がないため、古い音声のrevisionを偽って更新せず既存ファイルを保持。詳細はrun内narration_approval_through_scene80.json。
