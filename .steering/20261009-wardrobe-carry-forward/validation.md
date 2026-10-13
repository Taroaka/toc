# 検証

- toc-video-gen / toc-image-gen: quick_validate passed。
- 登録済みの2スキルは変更前hashを検査し、退避後にatomic更新。repo版とのSHA-256一致を確認。
- validate-pointer-docs.py / git diff --check passed。
- 衣装変更後の継続、脇役を含む人物別対応、集合名の一人画像、左右の入れ替わり、開始/中間/終了の不一致、衣装が変わらないcutへの不要な変身追加を手順で区別。
- 共通設計に作品固有の色や人物を固定せず、今回の具体的対応は既存run内のcontinuity記録を参照。
- runtimeコードや生成APIは変更・実行していない。今回の検証は文書・スキルの形式/同期/内容確認であり、生成品質を保証する自動テストではない。
