# Compiled-v2 Recompile Migration Requirements

## Goal

Frontend の scene prompt 再生成を、`image_api_prompt_v2` の最終文字列直接編集から、`first_frame_visual_plan` 更新、canonical compiler 再実行、manifest/request/snapshot 同期更新へ移行する。

## Success criteria

- scene v2 item は `video_manifest.md` の visual plan と compiled payloadを同時更新する。
- `toc.image_prompt_compiler.compile_image_api_prompt_v2` を唯一のcompilerとして使う。
- request markdown と snapshot は full materializationで再生成し、未選択itemを欠落させない。
- manifest/request/snapshot のいずれかが失敗した場合は3成果物をrollbackする。
- asset v1 prompt再生成は既存互換を維持する。
- frontend はrecompiled/direct_updateを表示上区別し、再取得したrequestを正本として使う。
- テスト中に画像生成や外部通信を行わない。

## Scope

- `server/codex_app_server.py`
- `server/image_gen_app.py`
- `server/web/src/main.tsx`
- 関連テストとcanonical docs

## Out of scope

- asset requestのv2化
- 画像生成の自動開始
- scene/cutの人物・小道具binding変更
- semantic QA gate自体の変更
