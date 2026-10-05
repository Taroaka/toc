# Design

Resolve omitted B-roll narration at manifest consumer boundaries using one shared predicate and a derived intentional-silence mapping. Keep explicit narration objects (text, output, provider, revision) unchanged. Project an omitted script narration into an explicit B-roll silence contract during ordinary script sync. Do not claim human confirmation. Preserve legacy non-B-roll silence checks. Subtitle rendering is already opt-in via --srt; document independent optionality and regression-test all audio/subtitle combinations.

Consumers: manifest asset validation, duration measurement/sync, narration verification, frontend readiness/list/render freeze, narration authoring scratch.
