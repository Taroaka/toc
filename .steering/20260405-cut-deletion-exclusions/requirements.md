# Requirements

- story review で不要になった cut は、物理削除ではなく `cut_status: deleted` と `deletion_reason` を残して監査できること
- deleted cut は image request / video request / image generation / video generation / audio generation から除外されること
- 最終の `clips.txt` / `narration_list.txt` でも deleted cut が使われないこと
- どの cut が何から除外されたかを md レポートで確認できること
