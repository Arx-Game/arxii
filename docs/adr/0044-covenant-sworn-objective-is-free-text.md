# Covenant sworn objective is recorded as free text

A covenant's `sworn_objective` is currently a free-text `TextField` that fires no completion or
dissolution events, so an objective being "met" never auto-ends the covenant; we chose this over a
structured goal model wired to completion events, which would push covenants toward being
"completed" rather than enduring. A structured `SwornObjective` FK is a roadmapped future slice, so
treat the free-text form as the present decision, not a permanent one.

> Status: accepted · Source: covenants.md · Confidence: derived-from-roadmap, verify against code
