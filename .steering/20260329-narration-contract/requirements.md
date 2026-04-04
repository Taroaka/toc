# Requirements

## Goal

ナレーション原稿の生成前に、scene/cut ごとの「done 条件」を generator と evaluator が共有できるようにする。

## Requirements

- narration node ごとに契約を持てる
- 契約は source manifest に保持する
- multiagent narration flow では scratch 段階で契約を先に書ける
- evaluator は契約の未定義、must cover 未達、must avoid 違反を検出できる
- 契約は高レベル実装を縛りすぎず、「何を伝えるべきか」「何を避けるべきか」を中心に定義する
