# Cut Prompt Reference Files Summary

このzipは、ToCの物語制作パイプラインで「cut」を設計・レビュー・画像生成・動画生成へ渡すための参照ファイルをまとめたものです。

## Cutの意義

cutは、sceneを実際の映像制作に落とし込む最小の演出単位です。sceneが物語上の大きな責務、感情の転換、出来事のまとまりを定義するのに対して、cutは「そのsceneの中で、1つの視覚的・感情的・時間的ビートをどう成立させるか」を定義します。

よいcut設計は、後段の画像生成・動画生成・ナレーション・編集を安定させます。sceneだけでは抽象度が高すぎて、各フレームで何を見せるべきか、どの情報を持ち越すべきか、どこで次のcutへ渡すべきかが曖昧になります。cutはその曖昧さを減らし、物語の意味を映像の作業単位へ分解する役割を持ちます。

## Sceneとの違い

- scene: 物語全体の中での大きな役割、出来事、感情の転換、構造上の位置を決める。
- cut: scene内の1ビートを、静止画・動き・音声・編集へ渡せる粒度に分ける。

sceneは「何が起きる場面か」を決め、cutは「その場面をどの順番で、どの画として、どの動きで見せるか」を決めます。

## 重要なフィールド

改善版では `cut_contract` を正本にし、既存 reader 向けに `scene_contract` を互換 alias として残します。

- `cut_function`: そのcutが担う物語上の機能。setup、pressure、threshold、turn、payoff、reaction、handoffなど。
- `viewer_contract.target_beat`: そのcutで成立させる具体的なビート。
- `viewer_contract.screen_question`: 視聴者がそのcut中に追う問い。
- `viewer_contract.dramatic_job`: そのcutが終わった時に物語上達成されているべき仕事。
- `viewer_contract.visual_proof`: 映像だけでbeatが成立したと分かる証拠。
- `first_frame_contract.first_frame_brief`: p600画像生成で使う、最初の1フレームの静止画指示。
- `first_frame_contract.action_completion_state`: stillが行為前、途中、余韻のどこかを固定する。
- `motion_contract.motion_brief`: p800動画生成で使う、最初の1フレーム以降の動きの指示。
- `narration_contract.role`: p700ナレーションが担う setup/fact/emotion/contrast/aftertaste/silent の役割。
- `continuity_contract`: cut間で維持する人物状態、物、位置、時間、光、音。
- `downstream_handoff`: p500/p600/p700/p800へ渡す契約。

## motion_briefの扱い

`motion_brief`はp800動画生成専用です。p600画像生成では参照しません。

理由は、画像生成はステートレスな1枚目のフレーム生成であり、1フレーム目以降の動きの情報を混ぜると、静止画プロンプトが未来の動作や時間変化を含んで曖昧になります。p600は`first_frame_brief`から最初の画を作り、p800が`motion_brief`を使ってその画を動かします。

改善版では、この分離を `first_frame_contract` と `motion_contract` に分けて表現します。

実際の request materialization では、`scripts/generate-assets-from-manifest.py` が `cut_contract` を読みます。画像requestには `viewer_contract` / `cinematic_contract` / `continuity_contract` / `first_frame_contract` の可視要件だけを足し、動画requestには `motion_contract.motion_brief` と `end_state` を足します。

## Review Gate

p420 cut blueprintには、お願いレベルではなくgateとしてレビュー観点を入れています。レビューは次の観点に分かれます。

- `cut_intent_isolation`: 1 cutが複数の意図を抱えすぎていないか。
- `beat_ladder_coverage`: scene内のビートが不足なく段階化されているか。
- `first_frame_motion_readiness`: `first_frame_brief`と`motion_brief`の責務が分かれているか。
- `multimodal_contract_coverage`: 画像・動画・音声・編集へ渡す契約が揃っているか。
- `duration_density_and_handoff`: cut数、尺、情報密度、次cutへの引き渡しが成立しているか。
- `coverage_plan_complete`: scene obligationがcut列へ割り当てられているか。
- `continuity_contract_complete`: cut間のstart/end/carry-forwardが成立しているか。
- `narration_contract_complete`: narration roleまたはsilent reasonがあるか。
- `downstream_handoff_complete`: p500/p600/p700/p800に渡せるか。
- `triangulation_review_ready`: image/narration/motionの三者整合をレビューできるか。

p400のreview loop integrityでは、p420レビューにこれらのfocus markerと`## Cut Blueprint Gate`がない場合に不備として検出します。

さらにp600画像プロンプトレビューでは、画像プロンプト本文に`motion_brief`相当の未来動作・時間変化指示が混入している場合、`prompt_leaks_motion_brief`としてhard findingにします。

## 読む順番

1. `docs/script-creation.md`
   cut設計が物語制作全体のどこに入るかを確認する入口です。

2. `docs/implementation/scene-loop.md`
   p400/p420/p600/p800の流れ、sceneとcutの関係、レビューgateの位置を確認します。

3. `docs/implementation/cut-loop.md`
   p420の正本です。coverage planning、cut数、gate、blocking reason keyを確認します。

4. `workflow/cut-blueprint-template.yaml`
   `cut_contract` v2.1 の完全な構造を確認します。

5. `docs/implementation/cut-to-image-narration-video.md`
   p420からp600/p700/p800へ渡す翻訳ルールを確認します。

6. `workflow/script-template.yaml` と `workflow/scene-outline-template.yaml`
   cut blueprintの構造と、scene設計からcut設計へ渡るフィールドを確認します。

7. `workflow/cut-handoff-matrix-template.yaml` と `workflow/cut-downstream-review-template.yaml`
   cut間handoffと、画像・音声・動画の三者整合レビューを確認します。

8. `workflow/scene-conte-template.md` と `workflow/scene-script-template.md`
   cutを絵コンテ・台本・制作指示に落とす時の見え方を確認します。

9. `docs/implementation/image-prompting.md`
   p600画像生成で`first_frame_brief`だけを使い、`motion_brief`を混ぜないルールを確認します。

10. `docs/video-generation.md`
   p800動画生成で`motion_brief`を使う位置を確認します。

11. `scripts/generate-assets-from-manifest.py`
   p600画像requestとp800動画requestの最終プロンプト合成で、`cut_contract` をどう使うかを確認します。

12. `toc/review_loop.py` と `toc/stage_evaluator.py`
   cut review gateの実装を確認します。

13. `scripts/review-image-prompt-story-consistency.py`
   p600画像プロンプトに`motion_brief`が漏れていないかを検出する実装を確認します。

14. `tests/`
   review gateと画像プロンプト検査がテストで固定されていることを確認します。

## このzipに含める意図

このzipは、他のエージェントへ「ToCのcut設計は何を担い、どのファイルを読めば実装意図が分かるか」を渡すための参照セットです。scene版と同じく、単なるファイル集合ではなく、制作パイプライン内でcutがどの責任を持つかを説明するための案内書を含めています。
