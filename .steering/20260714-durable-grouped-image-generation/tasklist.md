# Tasklist

- [x] 現行 app-server transport、bulk endpoint、依存 grouping、UI reload の失敗経路を特定する
- [x] requirements と design を固定する
- [x] 64 KiB 超の app-server notification と reader failure の回帰テストを追加する
- [x] bounded reader limit と reader error propagation を実装する
- [x] queue wait と generation execution の timeout を分離する
- [x] dependency group を使う bulk job scheduler の回帰テストを追加する
- [x] durable bulk job API と candidate image import を実装する
- [x] UI を job start/poll/reload reconnect へ変更する
- [x] targeted tests、backend tests、frontend build、security/diff review を完了する
- [x] 同一 turn の completed image item を turn 終了前に受領する
- [x] run 外の immutable first-image archive と receipt を実装する
- [x] candidate import を no-clobber 連番追記へ変更する
- [x] candidate 欠落時の再水和と semantic-blocked 時の実画像優先を実装する
- [x] job snapshot / UI の path 付き candidate を単調マージする
- [x] 消失した Cinderella 旧 run の scene1〜14 を Codex session と照合して archive へ復旧し、prompt hash 14/14 一致を確認して現行 run へ再取り込みする
- [x] archive-only run の一覧表示、marker 付き自動復旧、synthetic item/candidate API を実装する
- [x] receipt の SHA / destination / directory 対応を検証し、改ざんと path traversal を拒否する
- [x] run/kind scope を跨ぐ UI candidate 混入を防止する
