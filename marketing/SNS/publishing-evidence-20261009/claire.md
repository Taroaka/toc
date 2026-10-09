# Claire Vo / Codex Computer Use / TikTok・Instagram evidence

調査日: 2026-10-09 JST
対象: Claire Vo の本人サイトと、そこから確認できる一次リンク。公開ページの閲覧のみ。ログイン、投稿、アカウント変更、課金回避はしていない。

## 結論

2026-10-09 時点で、Claire Vo の本人サイトから確認できる「Codex Computer Use が TikTok または Instagram に動画を実際に公開した」という最近の一次証拠は見つからない。

- TikTok は **アップロード／composer へのステージングまで**。2026-08-05 の本人記録は明確に “uploaded it to the TikTok Studio composer **without posting**” と書いている。
- Instagram は本人サイトの本文・AI workflow 索引に言及がなく、Codex での動画投稿記録もない。
- 確認できた TikTok/YouTube の対象はすべて **動画**。09-22 の [Figma 透明 PNG workflow](https://clairevo.com/ai-workflows/make-a-transparent-livestream-overlay-in-figma-with-codex) は YouTube livestream overlay の素材であり、Instagram 画像投稿の証拠ではない。
- 最も強い最近の成功例は **2026-09-22 の YouTube Shorts**。Codex が YouTube Studio ブラウザで完成動画をアップロードし、タイトル・説明・関連する本編リンクを設定したという記録で、対象の TikTok/Instagram には外挿できない。
- Claire Vo のホームページで確認できる最新日付は **2026-09-23**。したがって「本人サイト上で 9/23 までを確認した」という時点上限を付ける。TikTok/Instagram 側の最新投稿がないと断定するものではない。

## 直接リンク付き証拠

| 日付 | 一次ページ | 確認できる事実 | 状態判定 |
|---|---|---|---|
| 2026-08-05 | [Assemble a recorded demo and handle its CapCut export with Codex](https://clairevo.com/ai-workflows/assemble-a-recorded-demo-and-handle-its-capcut-export-with-codex) / [ホームの 08.05 記録](https://clairevo.com/) | CapCut で縦動画を仕上げ、Codex が export controls を操作し、実ファイルの dimensions / frame rate / color space / audio を確認した。その後 TikTok Studio composer に upload したが **without posting**。 | **動画・TikTok・upload/stage のみ。publish ではない。** |
| 2026-09-22 | [Edit and publish captioned YouTube Shorts with Codex and FFmpeg](https://clairevo.com/ai-workflows/edit-and-publish-youtube-shorts-with-codex-and-ffmpeg) | 2本の録画から8本の縦 Shorts を作り、Codex が YouTube Studio で upload、title/description、本編リンクを設定。ページ本文は “publishing work” / “work through the upload screens” と記載。完成例への [YouTube Shorts リンク](https://www.youtube.com/shorts/Wbdh8bbrQnQ) もある。 | **動画・YouTube・公開運用の成功例。TikTok/Instagram の証拠ではない。** 個別8本の live/scheduled 状態までは列挙されていない。 |
| 2026-09-23 | [Claire Vo ホーム](https://clairevo.com/) / [AI workflows 索引](https://clairevo.com/ai-workflows) | ホームの最新日付は 09.23。AI workflow 索引には YouTube Studio と TikTok Studio の項目はあるが Instagram 項目はない。 | **本人サイトの確認上限。** |

## TikTok / Instagram のアカウント導線

- [Claire Vo の Linktree](https://linktr.ee/ClaireVo) は Instagram と TikTok のリンクを掲載している。リンク先は Instagram **https://instagram.com/clairevolawless**、TikTok **https://www.tiktok.com/@chiefproductofficer**。
- TikTok は公開プロフィールの取得が robots 制限、Instagram は fetch throttling で、今回の許可された読み取り経路から投稿一覧・投稿日・動画 permalink を検証できなかった。Linktree はアカウント名を特定する補助情報であり、Codex が投稿したという証拠には数えない。
- Claire Vo 本人サイトで `Instagram` を検索しても該当本文はなく、`TikTok` は 2026-08-05 の TikTok Studio 記録とフッターリンクのみ。したがって TikTok/Instagram の「最近の成功投稿」は **未検証** とする。

## プロンプトの出典と再利用可能部分

### TikTok 記録（出典ページが明示的に adapted）

2026-08-05 ページの `finish-and-verify-video.md` は、冒頭に **“Adapted from this workflow; not the original transcript.”** と明記されている。本人の逐語プロンプトではなく、公開用に再構成された brief として扱う。

含まれる再利用要素:

1. 入力された clips / editor project を確認し、録画順・発話・フレーミングを維持する。
2. HDR/SDR の不一致と音声処理を確認し、全体適用前に代表区間を見せる。
3. 承認後に指定先へ export し、実ファイルの dimensions、duration、frame rate、color space、video codec、audio を検査する。
4. publishing は人間に残す。upload を許可されても destination composer で停止し、post 前に止める。

### YouTube Shorts 記録（公開ページに載せた reusable brief）

2026-09-22 ページの `short-form-editing-brief.md` は、`Prompt` として掲載されているが、本文上は逐語 transcript か adapted prompt かを明記していない。従って「Claire の実際の指示そのもの」とは断定せず、**公開された再利用可能な brief** として扱う。

含まれる再利用要素:

1. source recording / moment / target length・9:16 を入力として固定する。
2. 完結した opening と natural ending を選び、話の意味を壊さない。
3. 台詞に合わせて speaker 全画面、固定 50/50、screen 全画面、読める close crop を使い分ける。
4. 顔・重要画面を避けた speech-timed captions を付け、実際の review file を人間が確認する。
5. feedback 後に音声・字幕・フレーミング・ending を再確認し、title/description/本編リンクを準備する。
6. “Upload or publish only after I approve the final clip and destination.” という承認ゲートを置く。

## ToC 用の安全な適用案（実績と未検証部分を分離）

ToC の skill は、Claire の **編集・品質確認・人間承認** を共通部分として採用し、プラットフォーム操作を adapter に分けるのが妥当。

1. **編集準備**: 元動画・使用区間・target platform・アカウント・縦横比・字幕方針を確定。発話の開始/終了と画面の読める範囲を先に決める。
2. **レンダーと人間レビュー**: 実ファイルを生成し、音声、字幕、画角、終端を視聴。人間が exact clip / caption / destination を承認するまで投稿操作をしない。
3. **ファイル検査**: dimensions、duration、fps、codec、color space、audio を実ファイルから読み、設定値だけで済ませない。HDR/SDR と音声処理を記録する。
4. **Computer Use でステージ**: 既に人間が開いた対象アカウントの TikTok Studio / Instagram の composer へ upload。caption、cover、tags、公開範囲などを入力しても、状態を `uploaded/draft/scheduled/published` に分ける。
5. **公開は別ゲート**: TikTok/Instagram への click-to-publish は、対象動画、caption、アカウント、公開範囲を読み上げて人間が明示承認した後だけ行う。成功を主張するには、公開画面で live 状態・投稿日（タイムゾーン）・対象動画の直接 permalink を確認する。
6. **証拠台帳**: `source`, `platform`, `account`, `media_type(video/image)`, `action`, `date/timezone`, `public_permalink`, `observed_state`, `human_approval` を保存する。直接 permalink がない `composer` や screenshot だけは publish evidence に昇格させない。

## 採用判定

**TikTok/Instagram への「Codex が動画を公開した」実績としては不採用（未検証）。** 採用できるのは、(a) 2026-08-05 の TikTok への upload/staging、(b) 2026-09-22 の YouTube Studio での短尺動画公開運用、(c) 両者から抽出した human-review-first の編集・検査・承認ゲートである。ToC の TikTok/Instagram adapter を「投稿済み」と宣伝する前に、対象アカウントで1本だけ実投稿し、公開 permalink と live 状態を人間確認して証拠台帳へ記録する必要がある。
