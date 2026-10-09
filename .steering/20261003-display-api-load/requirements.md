# Requirements
Keep image/narration display responsive without reducing generation-time validation. Avoid reparsing the same large manifest for each cut. Do not block the event loop with filesystem/CPU work. Coalesce overlapping display reads, invalidate parsed data when files change, and render available images without waiting for narration.
