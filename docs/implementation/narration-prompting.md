# Narration Prompt Projection

ナレーション作成promptは、story / scene / cut設計をそのまま文章へ連結しない。
設計keyをいったん用途別の authoring IR へ投影し、全編の語りを設計した後にspoken textへ変換する。

正本は `toc/narration_prompt_projection_registry.py` とする。新しい設計keyをp700で使う場合は、
runnerやcriticへ個別に追加せず、先にregistryへsource key、変換、review観点を登録する。

## 二つの判定軸

各keyは次の二軸を持つ。

- `authoring_relevance`: `required | conditional | none`
  - 原稿を判断するために必須か、値がある場合だけ使うか、p700では使わないか。
- `spoken_projection`: `derive | may_surface | must_not_surface`
  - 値から意味を導くか、必要なら本文へ現れてよいか、本文へ直接出してはいけないか。

意味reviewには第三の分類 `review_visibility: projection | review_only | none` がある。
画像promptやmotion promptはspoken textの素材にはしないが、音声が映像を先取り・重複していないかを判定するため
`review_only` contextとしてcriticだけが参照できる。

例:

- 歴史的時代は背景文脈として使うが、毎sceneで時代名を読み上げない。
- `time_of_day` は時間経過の理解に必要な場合だけ語る。朝光が画面で明白なら重複させない。
- `time_of_day_visual_basis` は光源・明るさ・影・色温度の visual review evidence であり、`review_only / must_not_surface` とする。照明設計をそのまま読み上げない。
- `location_sequence` は場所移動の理解に音声補助が必要な場合だけ候補にし、`location_mode` の設計labelは読み上げない。
- `narration_should_add` は、映像だけでは言えない因果、内面、時間、視点、意味、対比の候補にする。
- `visible_facts_in_frame` と `visual_beat` は画面理解用に読むが、原則として字幕のように言い直さない。
- `must_not_reveal`、withheld情報、forbidden reveal IDは境界判断に使い、本文へ漏らさない。
- motion promptとprovider画像promptはspoken textの素材にしない。

## 作成とreviewの対称性

`scratch/narration/authoring_prompt.md` とp720 semantic review packは、同じregistryから
`narration_prompt_projection_registry_v1`を生成する。物語・scene・cutの意味契約は同じprojectionを使う。
semantic reviewerには、それに加えて音声と映像の距離を評価するための `review_only` visual contextを渡す。
この追加contextを原稿のmust-cover素材として扱ってはいけない。

projectionはmanifest-global、scene、cutの三層に分ける。時代・結末は全編で一度、時間帯やscene intentはsceneで一度、
cut-local contractだけをcutごとにmaterializeする。registry catalogもsemantic packのtop-levelへ一度だけ置く。

registryへkeyを追加した場合は、少なくとも次をテストする。

- 空のconditional valueがpromptへ出ない。
- required / candidate / constraint / do-not-caption / delivery / excludeのbucketが正しい。
- `must_not_surface`値がspoken textの指示として扱われない。
- authoring promptとsemantic packが同じprojection contractを持つ。
- projection対象値の変更でsemantic input hashがstaleになる。

## 全編-first

key projectionはcutごとの独立作文を許可する仕組みではない。先にaudience promise、narrator bible、
open loop/payoff、scene attention arc、因果handoff、silence budgetを決め、continuous full draftを作る。
その後でspanとcut anchorへ分割する。最終的な合格条件は、局所keyの充足と全編の声の一貫性を同時に満たすこと。
