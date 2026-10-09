# Tasks

- [x] Author entrypoint, platform references, record contract and source notes.
- [x] Validate frontmatter, references and discovery links.
- [x] Review routing and failure cases against task intent.
- [x] Explain activation and disclose live-platform validation pending.


## Validation

- Installed skill passes quick_validate.py using the environment Python with PyYAML.
- All relative reference links resolve; openai.yaml implicit invocation enabled; project discovery symlink resolves to canonical skill; installed files match staging.
- Pointer docs validator passed. Initial elevated Python lacked PyYAML; validation was rerun successfully with the available environment interpreter. No dependency installed.
- Manual scenario review: research-only and schedule-planning prompts excluded; prepare does not publish/schedule; changed plan requires renewed review; missing schedule UI does not trigger immediate posting; post-submit timeout remains unknown and is not retried; successful sibling platform is skipped on resume; concurrent input forbidden.
- No live account setup, file upload, scheduled publication, or public post performed. Both platform routes require first-use runtime validation.
