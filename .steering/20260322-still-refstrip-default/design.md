# Design

- Extend the character bible in memory before asset-guide application so that existing sibling refstrip files are added to each character's `reference_images`.
- Only add a refstrip when the derived file actually exists under the current run directory.
- Keep video behavior unchanged; this change targets still-image reference injection.
- Update the image prompting and run docs to state that character stills automatically include refstrips when available.
