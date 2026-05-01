# YouTube チャンネル公開導線設計

最終更新: 2026-04-26
用途: 初回公開前に、チャンネルページを `着地ページ` として成立させるための設計メモ。

---

## 1. 考え方

新規 YouTube チャンネルは `動画1本` で見られるのではなく、`チャンネル全体の第一印象` で判断される。

初見の人が数秒で理解できるべきことは3つ。

1. これは誰向けか  
2. 何が見られるか  
3. 次に何を見ればいいか

---

## 2. launch 前に必須の面

| 面 | 役割 | launch 前に必要か |
|----|------|------------------|
| Profile | identity と trust | 必須 |
| Channel trailer | 非登録者向けの入口 | 必須 |
| Featured video | 既存訪問者向けの次の1本 | 必須 |
| Playlists + sections | 回遊導線 | 必須 |
| Posts / 追加 section | 補助導線 | 後回し可 |

---

## 3. launch の推奨順

1. ブランドの約束を固める
2. 初期コンテンツ群を用意する
3. Home tab を構成する
4. trailer と featured video を分ける
5. playlist section を並べる
6. `start here` 動線が見える状態で公開する

---

## 4. 初期コンテンツ群の考え方

`最初の1本だけ` では、見終わったあとに次の行き先がない。

小規模 launch でも、次の組み合わせを推奨する。

- 旗艦となる長尺動画 1 本
- 関連する補助動画または Shorts 2〜4 本
- それらを束ねる playlist 2〜4 個

`にわかのAI` なら初期形はこれでよい。

- flagship: `浦島太郎` 本編
- support: `制作の裏側` 1本、Shorts 1〜2本
- playlists: `まず見る3本 / AIでつくる民話・神話 / 制作の裏側 / Shorts`

---

## 5. trailer と featured video の役割分担

### Channel trailer

- 非登録者向け
- チャンネルの約束を短く説明する
- 新作告知ではなく `このチャンネルは何か` を伝える

### Featured video

- 既存視聴者向け
- 今見てほしい1本を置く
- 最新作、代表作、シリーズ導線のいずれかを担わせる

---

## 6. Home tab の初期構成

初期段階では section を増やしすぎない。
3〜5 個で十分。

推奨構成:

1. Trailer / Featured video
2. `Start Here`
3. `AIでつくる民話・神話`
4. `制作の裏側`
5. `Shorts`

---

## 7. launch 前に固定すべきこと

- タイトルのトーン
- サムネイルのトーン
- playlist の命名ルール
- top page の section 順
- 最初に見せる動画

`公開後に調整できること` と `公開前に固めるべきこと` を混ぜない。

公開前に固めるべきなのは `約束` と `導線`。
公開後に調整するのは `CTR 改善` や `retention を見た微調整`。

---

## 8. 後回しでよいもの

- section の細かい増設
- Community posts
- trailer の差し替え
- featured video の差し替え
- playlist の細分化

---

## 9. launch packaging の失敗例

- top page が初期状態のまま
- trailer がなく、初見で何のチャンネルか分からない
- 動画1本しかなく、次のクリック先がない
- playlist があるが、意味のない箱になっている
- サムネとバナーのトーンが一致していない

---

## 10. にわかのAI の推奨初期形

- trailer: `にわかのAIとは何か` を伝える短い紹介動画
- featured video: 代表作または最新の旗艦動画
- playlists: `まず見る3本 / AIでつくる民話・神話 / 制作の裏側 / Shorts`
- sections: 上の4本をそのまま top page に出す

---

## 11. 次に読むもの

- ブランドと初期設定 → `channel-branding-and-setup.md`
- 運用と policy → `channel-policy-and-ops.md`
- 公開前の実務 → `upload-checklist.md`
