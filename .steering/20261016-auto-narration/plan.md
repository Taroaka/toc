# Frontend automatic narration

User outcome: frontend creation continues after verified images to narration audio; resume the existing run without regenerating images.

Design: add p730 as the default normal-create and resume target, retaining explicit p650/p680 image-only behavior. Reuse canonical script text (including nested p400 audio), frontend revision saving, durable narration bulk candidates and provider settings. Preserve authored silence and existing current audio/candidates. Candidate generation does not fabricate listening or adoption. Report failures at p710/p730 without invalidating completed images. Resume uses persisted media operations before any new provider submission.

Tasks: add regression tests; implement shared continuation and create/resume integration; update UI resume target and docs; run affected tests and code review; generate current run audio and verify bytes/duration/hash.
