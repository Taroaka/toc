# Requirements

- scene image prompt は動画生成の最初の1フレームとして妥当でなければならない
- カット全体の出来事を完了形でそのまま still prompt に写してはならない
- mid-action な scene image prompt は evaluator で検出できること
- request 本文の first-frame 具体化はコードの定型変換ではなく、人レビューと自然言語エージェントの責務として扱うこと
