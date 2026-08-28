# ToC marketing image-volume positioning design

更新日: 2026-08-08

注記: 制作形式は、`.steering/20260809-marketing-two-production-modes/` の決定により、画像一括生成と動画制作の2つへ更新された。

## Message hierarchy

```text
Purpose
  人の心を動かし、人生を豊かにする。

0 second
  あなたの想いを、映像に。

3 second
  一枚の画像から、一本の動画まで。

10 second
  企画、構成、画像、動画、音声、編集を、ひとつの制作フローへ。
```

## Capability architecture

```text
brief / purpose / audience
  -> image_batch
       managed items / variants / review / provenance / reuse
  -> video
       structure / image / motion / voice / edit / render
  -> integrated
       shared assets / visual rules / approval / next production
```

## Marketing boundary

- `大量` は量だけを価値にしない
- public default は `必要な画像を、まとめて。`
- image-volume proof は generated count と accepted count を分ける
- low-quality mass output、unbounded variant、review なし生成を強みにしない
- provider / worker count は Hero ではなく mechanism / proof で必要な場合だけ説明する

## Projection boundary

- Workstream 1 は category、message、offer hypothesis、claim boundary を所有する
- Workstream 2 は common / persona LP へ image and video proof、format selection、form contract を投影する
- Workstream 3 は image proof inventory、campaign、measurement を更新し、publish-ready evidence を返す
