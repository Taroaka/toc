# Design: image prompt collection first

## Artifact

- Add a script that reads a manifest and writes a markdown prompt collection.
- Default scope is `still_image_plan.mode == generate_still`, because those are the paid stills that require review.

## Output format

For each selected cut, write:

- `scene/cut`
- `output`
- `narration`
- `rationale`
- raw `image_generation.prompt`

## Docs update

- `docs/how-to-run.md`: insert prompt collection generation before image generation.
- `docs/implementation/image-prompting.md`: state the canonical order as
  `select targets -> export prompt collection -> review -> generate images`.
- `workflow/playbooks/image-generation/reference-consistent-batch.md`: add prompt collection export to the steps.
