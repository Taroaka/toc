# 再開APIのロック競合

- 2026-09-27 15:59前後の再開要求がHTTP500になった原因は、p400実行中のdirectory flockを `_retain_frontend_create_run` が取得できず、FrontendCreateLockOwnedErrorがAPIのtryより外で漏れたこと。
- 入口でこの型だけを捕捉し、HTTP409と「すでに実行中」の説明を返す。
- OS flockを保持した実HTTPテストで500を再現してから修正。ジョブ・stateを新規変更せず、元のロックが維持されることも確認。
- 対象runはstory.mdとvisual_value.mdが完成し、cinematic authoringのプロセスが存在する。最後のCodex警告は15:59:05のwebsocket idle timeout / stream retry。
- 稼働中のrun・ロック・プロセスは変更しない。常駐APIへの反映には後続の安全なサーバー再起動が必要。
