# ADR-4532-A: House aspects are charter questions and facets; aspect is the check archetype only

**Date:** 2026-10-21
**Status:** Accepted (ApostateCD, in session)
**Issue:** #4532 (relates ADR-0101, ADR-4205, #2079)

## Decision

"Aspect" meant two things: the check-side archetype that boosts matching checks (`Aspect`,
`PathAspect`, `CheckTypeAspect`, the bigger, older, player-facing surface) and the authored
catalog choice on a house template. The house side is renamed and the word is left to the
checks. A template's authored question is a **charter question** (`HouseCharterQuestion`), its
catalog of answers its **options** (`HouseCharterOption`), and a house's picked answer a
**facet** (`OrganizationFacet`; on a founder's claim, `HouseClaimFacet`). The template's field
is `charter_questions`, a house's answers are `facets`, a claim's picks `facet_picks`. The
almanach already called a picked row a facet and the founder's answers the charter, so the code
is named for what it already said. Rename only: migrations are `RenameModel`/`RenameField`, no
data moves, no behavior changes.

## Rejected

Renaming the check side: older, larger, on the sheet, and the check-type tagging plan leans on
it. Leaving both and marking the glossary: the maintainer, 2026-10-21, "Rename the house side to
charter question and facet, file it."
