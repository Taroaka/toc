# Optional B-roll audio and subtitles

- B-roll may omit narration/audio and subtitles independently. Supplied media stays intact.
- Use the existing `a_roll_or_b_roll: b_roll` discriminator; document a canonical cut-contract location and read the existing image shot-design projection. Do not infer B-roll from prose, empty characters, or generic cut roles.
- Missing A-roll narration remains an error. Malformed/explicitly requested narration must not be silently dropped.
- Audio-free B-roll contributes its positive declared video duration; no TTS request is required. Mixed rendering preserves the silent interval.
- No production run, provider call, or deployment is part of this change. Baseline: Taroaka/toc main b3f215128f14e6afe3e96e530368295af6eb4112.
- On 2026-10-05 the user authorized applying the prepared patch and a normal push to main. Validate in an independent checkout and preserve all existing Mac edits; never force-push.
