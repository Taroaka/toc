# 音声タブ工程ゲート / 音声プロンプト作成 実装メモ

## 目的

フロントで画像生成結果を表示できる状態と、ToC 通常工程として「画像レビュー完了後に音声レビューへ進める状態」を分離する。

現状は画像 candidate が見えていれば音声タブで `ナレーション文面` / `TTS文面` を編集して音声生成できるが、これは通常 ToC 工程の `p680 image human review handoff -> p700 narration runtime` を必ずしも通っていない。音声タブは移動可能にしつつ、準備不足なら生成操作を blocked にし、準備完了後に通常工程と同等の音声プロンプト作成へ進ませる。

## 目指す UX

- `音声` タブ自体は常に開ける。
- シーン画像が未生成、または全 cut の採用画像が確定していない場合:
  - 音声生成ボタン類は disabled。
  - 音声タブ内に blocking panel を表示する。
  - 表示文言例: `シーン画像の生成・採用が完了していません`。
- 全 scene cut の採用画像が確定している場合:
  - `音声プロンプトを作成` ボタンを表示する。
  - これを押すとバックエンドで通常 ToC 工程と同じ扱いで、画像の人レビューが終わった状態として次の音声人レビュー直前まで進める。
- 音声プロンプト作成済みの場合:
  - `ナレーション文面` / `TTS文面` を表示する。
  - この状態で初めて `このcutの音声生成` / `全cut音声生成` を有効化する。

## 判定ルール

「シーン画像が生成されている」は単なる candidate の存在ではなく、採用画像が確定していることを条件にする。

推奨判定:

- 対象は `items.filter(isSceneCutItem)`。
- 各 item について、`selectedCandidatePath` または `existingImage` があり、かつ `output` があること。
- 可能なら `selectedCandidatePath` が manifest / request draft に保存済みであることを backend 側でも検証する。

未確定の候補がある状態では、音声プロンプト作成も音声生成も許可しない。

## フロント実装案

対象: `server/web/src/main.tsx`, `server/web/src/styles.css`

- `narrationReadiness` を `useMemo` で計算する。
  - `sceneItemsTotal`
  - `adoptedSceneItems`
  - `missingSceneItems`
  - `allSceneImagesAdopted`
  - `narrationPromptReady` もしくは `hasNarrationText`
- `NarrationCutCard` の生成ボタンは `narrationPromptReady && allSceneImagesAdopted` の時だけ有効にする。
- 音声タブ上部に状態 panel を置く。
  - 未準備: blocker panel
  - 画像採用済み / 音声プロンプト未作成: `音声プロンプトを作成` CTA
  - 作成済み: 通常の音声生成 UI
- `音声プロンプトを作成` 押下時:
  - 現在の画像レビュー draft を保存する。
  - 新 backend endpoint に scene items と採用画像情報を渡す。
  - 返却された `narration-items` / `progress` を反映して音声タブを更新する。

## バックエンド実装案

対象: `server/image_gen_app.py`

新 endpoint 案:

```http
POST /api/image-gen/narration-prompts/create
```

payload 案:

```json
{
  "run_id": "...",
  "items": [
    {
      "item_id": "scene10_cut1",
      "selected_candidate_path": "candidates/...",
      "output": "assets/scenes/scene10_cut01.png"
    }
  ],
  "note": "frontend image review completed before narration prompt creation"
}
```

処理:

- 全 scene cut の採用画像が確定しているか検証する。
- frontend review draft を保存する。
- 通常 ToC 工程の画像レビュー完了相当の state を append する。
- 通常の p700 系処理と整合する形で `narration.text` / `narration.tts_text` を manifest に materialize する。
- `state.txt` / `run_progress` を `p720` ないし `p750 awaiting human review` 相当に更新する。
- `GET /api/image-gen/narration-items` が作成済み narration text を返すようにする。

注意:

- 既存 `narration-generate` は音声ファイル生成まで行う endpoint。今回の CTA はそれより前段の「音声プロンプト / narration text 作成」に分ける。
- 既存 `video-prompts/create` が frontend review 保存 -> request/materialize -> state append の類似例。
- TTS 実生成では現状 `tts_text || text` が ElevenLabs の `text` payload に渡る。

## TTS / ElevenLabs の現状

- フロント payload:
  - `text: item.narrationText`
  - `tts_text: item.narrationTtsText || item.narrationText`
- backend:
  - `spoken_text = request.tts_text or request.text`
  - `prepare_elevenlabs_tts_text()` で空白正規化と発音辞書 alias 置換
  - `ElevenLabsClient.tts(text=prepared.text)` を呼ぶ
- `voice_id`, `model_id`, `language_code`, `voice_settings` は provider/client 側に存在するが、現フロント生成経路では UI から構造化指定していない。
- `toc/script_narration.py` には `elevenlabs_prompt.voice_tags` を TTS text に materialize する helper がある。今回の「音声プロンプト作成」はこの既存思想に寄せるのが望ましい。

## 関連ファイル

フロント:

- `server/web/src/main.tsx`
- `server/web/src/styles.css`

バックエンド / API:

- `server/image_gen_app.py`

ToC 工程 / 音声 / レビュー:

- `toc/run_index.py`
- `toc/review_loop.py`
- `toc/stage_evaluator.py`
- `toc/script_narration.py`
- `toc/tts_text.py`
- `toc/providers/elevenlabs.py`
- `toc/semantic_pack_narration.py`
- `toc/harness.py`

仕様 / テスト:

- `docs/data-contracts.md`
- `tests/test_image_gen_server.py`
- `tests/test_script_narration.py`
- `tests/test_tts_text.py`
- `tests/test_semantic_pack_narration.py`
- `tests/test_run_index.py`
- `tests/test_review_loop_contract.py`
- `tests/test_toc_immersive_ride_scaffold.py`

## 受け入れ条件

- 画像 > シーンで全 cut の採用画像が確定していない run では、音声タブ内の音声生成操作が disabled になる。
- 全 cut 採用済みの run では、音声タブに `音声プロンプトを作成` が出る。
- `音声プロンプトを作成` 後、`ナレーション文面` / `TTS文面` がロードされ、音声生成が有効になる。
- backend state / run progress が通常 ToC 工程の p700 系と矛盾しない。
- `narration-generate` は引き続き `tts_text || text` を読み上げ本文として使う。

## 推奨テスト

- `npm run build` in `server/web`
- `python scripts/validate-pointer-docs.py`
- `pytest tests/test_image_gen_server.py`
- `pytest tests/test_script_narration.py tests/test_tts_text.py tests/test_semantic_pack_narration.py`
- `pytest tests/test_run_index.py tests/test_review_loop_contract.py`
- 必要なら `pytest tests/test_toc_immersive_ride_scaffold.py`
