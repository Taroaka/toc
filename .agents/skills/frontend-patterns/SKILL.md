---
name: frontend-patterns
description: Choose React/Next.js component, state, data-fetching, and rendering patterns when designing or diagnosing frontend behavior.
---

# Frontend Patterns

Use the project's existing components, state ownership, and libraries as the starting point. Choose a pattern to solve a concrete behavior or measured performance problem; the examples do not prescribe new dependencies or a rewrite.

Read only the relevant reference:

- [Components and state](references/components-state.md): composition, custom hooks, context/reducer, and async fetching.
- [Rendering performance](references/performance.md): memoization, lazy loading, and long lists. Measure the affected interaction before adding caches or memoization.
- [Interaction and accessibility](references/interaction.md): forms, error boundaries, animation, keyboard navigation, and focus.

Preserve loading, error, empty, and keyboard states for the interaction being changed. Verify that interaction using the existing test or browser setup; a copy edit does not need an architecture review.
