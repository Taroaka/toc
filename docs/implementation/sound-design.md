# p860 BGM・SE

物語全体の制作順は `p840 動画生成 → 動画のユーザー承認 → p860 BGM・SE → p910 結合入力 → p920 最終結合`。
BGMとSEはともにp860内で提案、生成、試聴、採用、配置設定を行う。p850は廃止したまま。

## 物語上の役割を先に設計する

設計前に [BGM・SEの研究資料](../research/film-sound-emotion.md) と
[意図とspottingの手引き](../../workflow/playbooks/sound-design/affect-and-spotting.md) を読む。
BGM/SEの役割は、観客の感情だけでなく、注意、人物理解、因果、身体性、空間、予期、回想、余韻を支えること。
実際の観客の感動は保証しない。意図した効果と、試聴で受け取られた効果を分ける。

- p400: 既存の`audio_intent`等の正規欄で音の役割、視点、言葉との分担、音を引く区間を考える。生成や最終秒数の確定は行わない。
- p860: 確定映像と実音声でspottingし、音の入口・変化・出口を出来事へ合わせる。必要なら [記入テンプレート](../../workflow/sound-spotting-template.md) をrunの`logs/sound_design/spotting.md`へ保存する。メモは判断の根拠であり、runtimeの正本は従来の`sound_design.json`。
- 各cueは「何を感じて/理解してほしいか」「何を最優先で聞かせるか」「なぜここで鳴らす/止めるか」を説明できるものにする。全場面にBGM/SEを追加する義務はない。
- BGMはcutごとに替えず、感情/理解の流れで継続・変化・停止を判断する。主題の再登場は対応する過去の場面を持たせ、独立生成でも同じ旋律になるとは仮定しない。
- SEは動作の発生位置、材質、距離、空間に合わせる。画面外の音もsource/演出上の根拠があれば使える。音だけで未設定の出来事や未開示情報を追加しない。
- 音楽なし・環境音のみ・全無音を区別する。元動画音声との重複、語りや台詞の聞き取り、終幕のフレーズと余韻を確認する。
- 終幕の感動を音量最大化と同一視しない。高揚、安心、切なさ、未解決など作品の結末に合う狙いを選ぶ。

### LLMが演出を判断し、コードが再現する

新規動画承認ではBGM/SEを自動で決めず、空のcue配列から始める。既存作品のcue/採用音源は保持する。
「LLMで音響案を設計して追加」は研究・本設計・spotting手引き/テンプレート全文、story、全active script cutの語り/音響/動作/開示契約、確定動画timeline、現在のcueと元動画音声、ユーザー要望を読み込む。
既存のread-only author runtimeと既定authorモデルを使用する。コードに感情→曲種の対応表は置かない。

LLMは`SoundDesignDraft`の全編intent、silence_regions、任意数のcueを返す。0cueも許可。
cueにはkind/label/source_selector/purpose/perspective/timing_reasonと生成指示・生成尺・配置尺・開始秒・音量・fade・loopを持たせる。
音源path、候補、採用状態は生成させない。コードは既知selector、有限の数値、provider尺、全編内の配置、fade等を検証する。
source_selectorは`full_run`または確定動画target。render unitはunitを参照し、元cutの出来事を理由欄で説明する。
一つのtargetに複数SE/BGMを置ける。配置時刻は全編の絶対秒で、cueはcutをまたいでよい。

提案は新規の未採用cueとして追加する。再設計でも既存cue、候補、mix、native_tracksは変更しない。
不要な下書きは明示削除する。silence_regionsは演出意図のメモであり、既存採用音を自動muteする指定ではない。
音源生成は別ボタンで行う。LLM設計失敗/不正出力を定型案で代替しない。

`logs/sound_design/design_<id>.request.json`に入力原本/設計書hash、revision、video hash、実promptを保存し、結果とauthor provenance、反映statusを別ファイルに残す。
LLM処理中はrun書込lockを解放し、反映直前にrevision/video hash/原本と設計書hash/plan hashを再確認する。
変更があれば出力だけを記録して反映を拒否する。同一runの同時設計は拒否する。通信切断/プロセス停止時にLLMを自動再送しない。

手動追加にも同じcue検証を使う。cue IDはサーバー側UUID。削除は`archived_cues`へ保存し音源bytesを削除しない。
生成中に削除されたcueの結果はstaleとして履歴へ保存し、active cueを復活させない。
メタデータのみの編集では音源を再生成しない。prompt/生成尺等が変わる場合は既存の候補無効化を適用する。
変更後はp860をdraft、p910/p920をpendingへ戻す。設計しただけで音源生成・採用・mixが完了したとは扱わない。

gain automation、source trim、stem分離は今回の対象外。必要なら別編集/追加実装と明示する。
通常の生成操作にLLMの感動採点や新しい承認gateは追加しない。

## 入力と承認

`video_manifest.md` のactive cutまたはrender unitを、最終結合と同じ順序で読む。
動画の存在・実測尺、current candidate revisionを確認し、selector、path、ファイルSHA-256、
生成指示、設定尺、ナレーション集合とtimelineをまとめた `video_set_hash` にユーザー承認を結び付ける。
画面が取得したhashと現在のhashが一致した場合のみ承認できる。動画・尺の変更後は再承認する。

## 正本と操作

`sound_design.json` (`schema_version: sound_design_v1`) が正本。

- `video_approval`: hash、actor、日時。
- `cues[]`: BGM/SE区分、元selector、編集可能な生成指示、生成尺、開始秒、再生尺、音量dB、fade in/out、loop。
- `candidates[]`: immutable ID、実測尺、path、bytes hash、provider payload/request hash、成否。
- `selected_candidate_id` と `enabled`: 最終結合へ渡す候補と使用有無。
- `revision`: 設定の楽観ロック。別画面の古い設定で上書きしない。
- `status`: draft/completed。設定の変更はdraftへ戻す。候補追加だけでは採用や設定確定を変更しない。
- `mix`: 最終合成の `narration` / `se` / `bgm` ごとの `volume_db`（−60〜+36dB）と `muted`。未指定は0dB・非ミュートで旧planと互換。個別cueの音量に加算し、元動画音声はSE系統に含める。個別cueも+36dBまで増幅可能。

承認直後は音楽/SEを決めない。LLMで設計するか手動で追加する。設計結果は未採用の下書きであり、音声providerは呼ばない。作品固有の分岐や固定対応表は設けない。
生成ボタンを押すと実際の音声候補を1本生成する。繰り返して複数候補を比較できる。
生成は自動採用しない。採用後に音量・位置などを保存し、「採用した音で確定」でp860を完了する。
不要な案は未採用のまま完了できる。追加音なしの場合は「BGM・SEなしで確定」を明示的に選ぶ。

動画承認が変わると旧planを `logs/sound_design/previous_*.json` に保存して新しい案を作る。
音声生成失敗時は旧候補を残して再生成できる。生成中に入力が変わった出力はstaleとして採用させない。

## Provider

既存の `ELEVENLABS_API_KEY` / `ELEVENLABS_API_BASE` を使用。
BGMは `POST /v1/music`、`music_v2_5`、`force_instrumental: true`、3〜600秒。
SEは `POST /v1/sound-generation`、`eleven_text_to_sound_v2`、0.5〜30秒。
いずれも `mp3_44100_128`。provider requestは呼出前に `logs/sound_design/*.request.json` へ保存する。
APIキーは保存しない。ffprobe、音声decodeとhashを検証し、`assets/sound/<cue>/<candidate>.mp3` に保存する。
メディア操作journal/実行leaseは既存runtimeと共用し、接続終了時も実行中の結果を保存する。

公式仕様: [Music](https://elevenlabs.io/docs/api-reference/music/compose)、
[Sound Effects](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert)（2026-10-07確認）。

## API / フロント

共通prefixは `/api/image-gen/sound-design`。

| Method / suffix | 操作 |
| --- | --- |
| GET（run_id） | 動画一式、承認状態、案、候補、設定、結合可否 |
| POST /approve-video | current動画の承認。新規BGM/SEは空から開始 |
| POST /design | 設計書を読むLLMで新規音響案を作り、未採用cueとして追記 |
| POST /cue-create | 独立したBGM/SEを手動追加。同じtargetへの複数追加可 |
| POST /cue-delete | cueをarchiveへ移す。音源ファイルは保持 |
| POST /cue | 指示・採用候補・配置と、任意のmetadata（名前/対象/狙い/視点/タイミング理由）を保存 |
| POST /generate | 保存された指示から候補生成 |
| POST /complete | 使用音の確定、または明示的な追加音なし |
| POST /mix | 3系統の音量とミュートを保存。revision/hash競合を拒否し、最終レンダーを未完に戻す |
| POST /mix-preview | 未保存の3系統設定を使った試聴動画をローカル作成。manifest/採用候補/工程完了状態を変更しない |

POSTはrun_id、video_set_hash、revisionを必須とし、generate/cue/削除はitem_idを持つ。designはinstructions、cue-createはCueDraftを持つ。
動画タブから「動画を確認・承認してBGM・SEへ」で進める。
最終タブはp860の確定を確認し、未確定ならBGM・SEへ誘導する。API側でも同じ条件を検証する。

## 最終音量ミキサー

最終合成タブでナレーション・SE・BGMを独立して調整し、「この音量で試聴」で映像付きのプレビューを作る。
これはリアルタイムのブラウザー側音声処理ではなく、最終書き出しと同じ `mix_audio` を使うローカルレンダー。
音量を変えたら以前の試聴結果は更新待ちとして表示する。「音量を保存して書き出しに使用」で明示保存するまで、最終レンダーを無効化する。
全体音量の明示保存は採用済みcueを変えないため、completedの音素材選択を維持する。生成指示・個別cue変更のdraft化は従来どおり。

プレビューはUUID付き `assets/test/mix_preview/` に保存し、動画・音声・設定の変更が途中で発生したら結果を返さず競合として扱う。
完成後はそのプレビュー専用の中間ファイルを除去する。元の音源と映像は変更しない。
共通のナレーションマスタリング後に3系統の音量を反映し、最後に音割れ防止limiterを適用する。既存の配置・loop・fade・元動画の音声・台詞のduckingも共通処理を使う。
プレビュー作成は生成AIを呼ばず、生成課金を伴わない。

## p910 / p920への受け渡し

動画候補の手動選択・編集で選択動画が変わると、p860の承認は再確認待ちになる。
候補編集と選択条件は[制作補助ツール](production-tools.md)を参照。

p910はp860のcurrent approval、completed状態、全採用候補のrequest hash/bytesを検証する。
選択した音声とmix設定を `logs/review/frontend/sound_render_*.json` 相当のrender reviewディレクトリに
`sound_render_v1` snapshotとして保存し、`soundPlan` / `soundHash` を返す。
実際の保存先はfreezeレスポンスを正とする。CLIも `freeze-approved-render-inputs.py` を通す。

`render-video.sh --clip-list ... --narration-list ... --sound-plan <soundPlan> --out ...` は
`mix-sound-design.py` を呼び、48kHz stereoに揃えたナレーションとBGM/SEをmixしてからmuxする。
BGM loop、SEの開始位置、trim/pad、音量、fade、limiterを適用し、承認動画全体の尺を保持する。
`video_generation.native_audio.mode`を明示した動画は、p860の「元動画の音声」で採用・消音・音量・fadeを設定できる。
旧runの未指定はoff。音声は単一のmix trackとして扱い、stemへ分離したとは扱わない。
`native_tracks`に選択した動画のbytes hash・音声stream identity・candidate revision・最終targetの開始秒と尺を保存する。
render unitの音はunitごとに一度だけ合成する。元動画の音は動画先頭を基準とし、ナレーションの既存offsetは変えない。
台詞を含むtrackでは、明示的に選択した場合だけナレーションをduckする。
必要な音声streamがない場合やsourceが変わった場合は、その素材を修正してから再確定する。
レンダー完了時にもcurrentな動画・ナレーション・音声設定のhashを確認する。
低レベルrendererの既存 `--bgm` / `--audio` は互換用。新しい制作フローではp860 snapshotを使用する。
