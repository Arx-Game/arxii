# 0193 — Stats store ×10 under the hood; skills store and display true value

**Status:** Accepted (2026-08-03, Apostate's ruling on #2894)

`CharacterTraitValue` holds one storage scale — the fine-grained 1-100 range —
but the two trait families *display* differently. **Skills show their true
stored value** (a skill of 35 reads 35): development moves them by single
points (11…19) and an XP unlock crosses the rung boundary to 20, so the
fine grain is player-visible by design. **Stats display single-digit and are
×10 under the hood** (strength 2 = stored 20): players allocate 1-5 dots, and
the ×10 conversion happens once at CG finalization so stats land on the same
storage scale as everything else. Strength 2 + weapon skill 35 = 20 + 35 = 55
check points. Character creation previously wrote stats at display scale — the
sole display-scale writer in the repo — which silently zeroed CG characters in
every storage-scale consumer (checks, encumbrance, health, stat modifiers,
thread anchor caps, trait predicates) and spawned per-consumer compatibility
guards. The alternative — declaring 1-5 the canonical stat storage — was
rejected: modifiers, DP level-ups, and `PointConversionRange` all already
operate on the ×10 scale. Stat display conversion happens at the edge via
`world.traits.models.display_trait_value` / `STAT_DISPLAY_DIVISOR`; authored
display-dot numbers (e.g. `MaturationStatCap`) convert at the comparison,
never at rest; skill display paths never divide. CG skills also bridge into
matching `CharacterTraitValue` rows at finalization — `perform_check` reads
only trait rows, and `DevelopmentPoints.award_points` increments those same
rows from the CG level onward.
