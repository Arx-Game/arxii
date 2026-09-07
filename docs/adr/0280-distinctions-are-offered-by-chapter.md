# ADR-0280: Distinctions are offered by CG chapter, not gated by a stage

**Status:** Accepted (#3675, 2026-09-07). Related ADR-0136 (the CG magic revamp this
extends), ADR-0277 (the questionnaire model whose answers open Lineage offers),
ADR-0278 (the handler pattern `GlimpseTag.offers` follows), ADR-0279 (enemy degrees
arrive as offers with source `enemy:<degree>`, the same shape this ADR gives every
other CG-earned distinction).

**Context.** The Distinctions stage was a standalone catalog browser, disconnected
from the prose sections that should have earned or explained a pick. Three separate,
unrelated couplings had each grown up to link one chapter's content to a distinction:
`BeginningTradition.required_distinction` (a name-matched FK gating the Unbound/
Orphaned Tradition drawback), `GlimpseTagDistinctionSuggestion` (a pairing table that
only suggested, never gated), and `OriginTemplateSlotChoice.grants_distinction`
(bundled-free only, #3660). None of the three could price a plain player choice, none
shared a source-provenance shape with the others, and a fourth chapter (Appearance,
the Actor's Sheet) had no coupling at all. Tehom's ruling on the demo: this is a UX
fix first, every CG chapter should be the place its own distinctions are picked, seen
with their effect and cost at the moment of choice, and every player-facing line
(schooling names, tradition-state wording) must be staff-authored, never printed from
what a character will discover in play.

**Decision.** One authored `DistinctionOffer` row per (distinction, chapter, opener):
`chapter` (`OfferChapter`: tradition_step/glimpse/lineage/appearance/actors_sheet) says
which CG chapter shows the line; `arrives_as` (`OfferArrival`) says whether it is a
priced `choice`, `bundled` free with its opener, or `carried` by a tradition-state pick
with no offer row of its own; an opener FK scoped to the chapter
(`schooling_line`/`glimpse_tag`/`origin_choice`) says what opens it, when the chapter
has one at all. Price is never typed as a number on the offer: a `choice` reads the
distinction's own `cost_per_rank`, a `bundled`/`carried` entry is free. Standard lines
are authored once and shared: `TraditionStateLine` (three rows, one per
`TraditionState`) carries the wording and drawback every Beginning's tradition-step
entry reads by default, with a `own_wording` override per pairing and never its own
price; `SchoolingLine` (three rows, rank 0-2) is the standard living-tradition
schooling set every Beginning reuses. A route closes distinctions by field
(`OriginTemplate.closed_distinctions`/`closed_reason`), never by a name match. One
module, `world.character_creation.offers`, is the sole reader (`offers_for`,
`closed_for`, `reconcile_offer_picks`), and `reconcile_offer_picks` runs after every
draft PATCH, tradition select, and once at the start of every finalize path, so a
picked distinction's provenance (`offer_ids`/`sources`/`arrivals` on its draft entry)
stays correct however the draft got there.

**Rejected: extending the three existing couplings separately.** Adding a chapter
field to each of `required_distinction`, `GlimpseTagDistinctionSuggestion`, and
`grants_distinction` would have kept three different provenance shapes, three
different price stories, and left Appearance/the Actor's Sheet with nothing. A
distinction offered from two chapters (a Glimpse tag and a Lineage answer both
suggesting the same one) would need a merge rule invented three times over instead of
once in `reconcile_offer_picks`.

**Rejected: wiring the `DistinctionPrerequisite` JSON evaluator.** A prerequisite rule
tree already existed on the model (`rule_json`, ADR-0007-compliant JSONField) but had
zero rows in production and no evaluator; building one would have added a second
"can the player have this" mechanism alongside offers, deciding visibility from a
predicate tree instead of from what the player is actually doing in the chapter
they're in. Deleted outright (migration 0111); the offer's opener check is the only
gate now.

**Rejected: per-tradition prices.** Letting `own_wording` also carry its own price
would have let a Beginning quietly reprice a drawback out of step with its own
`Distinction.cost_per_rank`, and given staff two numbers to keep in sync instead of
one. `own_wording` replaces only the words; the price always reads through to the
carried/granted `Distinction`.
