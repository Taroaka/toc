# ToC Public Site / LP Guide

更新日: 2026-07-19

`marketing/LP/` は、既存 ToC 制作フロントとは分離して公開する marketing site と persona-specific LP の正本を置く。

## Site job

訪問者に ToC の内部実装を説明することではなく、動画を速く簡単に作れる変化を見せ、次のどちらかへ進んでもらう。

- 副業の最初の1本を作る
- 自分のブランド動画を設計する

## Information architecture

```text
/
├── /for-side-business
├── /for-personal-brand
├── /examples
├── /how-it-works
├── /contact
├── /privacy
└── /thanks
```

- common home: brand, organic traffic, comparison, persona selection
- `/for-side-business`: side-business campaign landing page
- `/for-personal-brand`: personal-brand campaign landing page
- `/examples`: proof library; mythology is one example category
- `/how-it-works`: mechanism and human judgment
- `/contact`: native form

## Design rules

- Hero is the promise, not a company introduction
- Show `one-line idea -> completed video timeline` before the detailed workflow
- Lead with visitor outcome, then product value, then mechanism
- Keep side-business and personal-brand copy separate
- Use one signature motion, `Idea-to-Video Line`; keep other motion restrained
- Respect mobile, keyboard focus, reduced motion, readable contrast, and fast loading
- Do not use generic purple AI gradients, mythic ornaments, dashboard-first heroes, or unverified claims

## Conversion rules

- common CTA: `自分なら何を作れるか見る`
- side-business CTA: `副業の最初の1本を作る`
- personal-brand CTA: `自分のブランド動画を設計する`
- collect the video idea before long profile fields
- carry the idea and persona into the native form
- use a dedicated thank-you page and conversion event
- do not use Notion or Google Forms as the canonical public route

## Files

- `personas.md`: side-business / personal-brand persona, message, objection, proof contract
- `toc-marketing-site.md`: common site and persona LP copy / section contract
- `lead-form-schema.md`: native form, validation, event, and data contract
