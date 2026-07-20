# ToC native lead form contract

更新日: 2026-07-19

用途: 独立した ToC marketing site 内に実装する idea intake / lead form。Google Forms、Notion Forms、Typeform を canonical route にしない。

## Conversion principle

長い個人情報入力から始めず、visitor が作りたい動画を一行で入力するところから始める。

```text
persona selection
  -> one-line video idea
  -> minimum contact details
  -> consent
  -> thank-you page
```

## Step 1: purpose

Required, single select.

- `side_business`: 副業のために動画を作りたい
- `personal_brand`: 自分のブランドを構築したい
- `other`: その他

Preserve campaign-provided persona when the visitor came from a persona-specific LP. Allow editing.

Do not ask `あなたはどのタイプですか？`. Ask what the visitor wants to build:

- `副業の可能性を試したい`
- `自分のブランドを育てたい`

## Step 2: video idea

### `video_idea`

Required, 10–500 characters.

Label: `どんな動画を作りたいですか？`

Placeholder:

```text
例: 30代会社員向けに、睡眠改善を分かりやすく伝えるYouTube動画
```

### `target_audience`

Optional, 0–200 characters.

Label: `誰に届けたいですか？`

### `desired_format`

Optional, multi select.

- YouTube long-form
- Shorts / Reels / TikTok
- 解説・教育
- 商品・サービス紹介
- personal brand / thought leadership
- story / entertainment
- not decided

## Step 3: current obstacle

Optional, multi select.

- 時間がない
- 編集できない
- 企画や台本で止まる
- 生成AIツールが多すぎる
- 発信を継続できない
- ブランドの一貫性を保てない
- 外注費が高い
- 品質が不安
- その他

Use this for routing and product learning, not for manipulative messaging.

## Step 3a: persona-specific qualification

Show no more than two fields for the selected persona.

For `side_business`:

- `side_business_stage`: アイデアだけ / 制作途中 / 公開経験あり / 継続中
- `side_business_goal`: 最初の1本 / niche 検証 / 投稿継続 / 収益化検証

For `personal_brand`:

- `expertise_topic`: `何について知られる人になりたいですか？`
- `brand_video_goal`: 認知 / 信頼 / 問い合わせ / 教育 / launch support

Collect optional research fields such as weekly time, existing assets, desired cadence, channel URLs, and format preference only after lead submission or during follow-up. Do not turn the first form into a survey.

## Step 4: contact

### `name`

Optional, 0–100 characters.

### `email`

Required, normalized email address.

### `reply_preference`

Required, single select.

- 利用方法を知りたい
- 最初の1本について相談したい
- 開発・提供開始の案内だけ受け取りたい

## Step 5: source and consent

Hidden / derived fields:

- `landing_persona`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_content`
- `referrer`
- `landing_path`
- `submitted_at`
- `privacy_policy_version`

Required checkbox:

`プライバシーポリシーを確認し、入力内容の取扱いに同意します。`

Marketing email consent must be separate and optional:

`ToCの提供開始、制作事例、改善情報をメールで受け取る。`

## Validation and security

- client and server validation
- honeypot or equivalent hidden trap
- Cloudflare Turnstile or equivalent bot verification
- rate limit by normalized client signal
- idempotency key to prevent duplicate leads
- do not expose provider keys to the browser
- escape stored and rendered user input
- log consent version and acquisition source
- define retention and deletion process before launch

## Submit behavior

On success:

1. persist the lead
2. notify the operator
3. send a receipt email when deliverability is configured
4. emit `generate_lead` with persona and acquisition source, without raw personal data
5. navigate to `/thanks`

Success message:

```text
動画のアイデアを受け取りました。
入力内容を確認し、選択した案内方法に合わせてご連絡します。
```

On recoverable failure, retain the entered idea and explain the next action. Never clear the entire form after a server or network error.
