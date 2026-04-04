# Requirements

## Goal
追加された映像価値カットについて、ナレーションなしで動画尺を確保できるようにする。ただし、無音は人が意図したものだけを許可し、生成前に必ず確認できるようにする。

## Requirements
- 追加カットで narration を入れない場合でも、video_generation.duration_seconds を維持して動画生成できること。
- そのような cut は manifest 上で明示的に意図された無音であることを記録できること。
- TTS 生成前の preflight で、narration が空なのに意図フラグがない cut を失敗にすること。
- 最終音声連結時は、その cut の duration 分の無音が入ることを設計に明示すること。
- 既存の通常 spoken cut は従来どおり、音声実秒 + 余白に基づいて video duration を決めること。
- 追加の意図的無音 cut だけ、video duration > narration duration を許可すること。
