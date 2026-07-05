# ADR-0091: NPCAsset promotion is a plain NPCServiceOffer, in a new one-way-dependent app

## Status
Accepted

## Context
#1872 needed a "Cultivate as Asset" mechanic: post-interaction, once rapport
crosses a threshold and a capability trait gate is met, a PC can promote a
class-1 Functionary into a permanently-owned NPCAsset. Two hard-to-reverse
calls: (1) where the new NPCAsset model and its promotion logic live, and
(2) whether the trigger needed new session/eligibility infrastructure.

## Decision
1. `NPCAsset` lives in a new `world.assets` app, depending one-directionally
   on `world.npc_services` (Functionary, NPCRole, OfferKind),
   `world.scenes` (Persona), `world.character_sheets`
   (`create_character_with_sheet`), and `world.checks` (`perform_check`).
   `world.npc_services` has zero knowledge of `world.assets` — mirrors the
   `world.companions` precedent (the other half of the original #672).
2. "Cultivate as Asset" is modeled as three new `OfferKind` values
   (`INFORMANT`/`CONTACT`/`PERSONAL_FAVOR`) on the *existing*
   `NPCServiceOffer`/`available_offers`/`resolve_offer`/
   `dispatch_offer_effect` framework, not a new parallel eligibility
   pipeline. `NPCServiceOffer` already carries both gates this mechanic
   needs — `rapport_requirement` and `eligibility_rule` (a `min_trait`
   predicate) — evaluated purely against `session.role`, with no
   dependency on `npc_persona`. Which specific `Functionary` to promote is
   resolved at grant time from the PC's current location
   (`Functionary.objects.filter(role=offer.role,
   room=get_room_profile(character.location))`), which `place_functionary`'s
   `(role, room)` uniqueness constraint makes deterministic — no new field on
   `InteractionSession` was needed. That lookup deliberately does not filter
   on `is_active` up front: a promoter who already cultivated this
   Functionary deactivated it themselves, so the handler needs to see the
   (now-inactive) row to distinguish "you already did this" from "it's
   genuinely gone" — `is_active` is only re-checked, via a fresh `.exists()`
   predicate, after the per-promoter dedup check clears.
3. `NPCAsset` stores no `standing` field, despite the original design
   sketch listing one. `promoter_persona`/`asset_persona` is the same
   persona pair `NPCStanding` already keys on; ongoing affection is read
   through the existing `NPCStanding` row, created automatically by the
   existing `start_interaction`/`end_interaction` machinery the first time
   the PC interacts with the newly-named NPC.

## Alternatives rejected
- A new `InteractionSession`-scoped eligibility pipeline (extend the
  dataclass with a `functionary` field, thread it through `_stash`/
  `_rehydrate`, add a dedicated "end + check promotion" endpoint): works,
  but duplicates infrastructure `NPCServiceOffer` already provides and
  would have required touching the shared `(offer, persona)` effect-handler
  contract for every other handler's benefit.
- A `standing` field directly on `NPCAsset`: would drift from
  `NPCStanding` as the single source of truth for the same persona pair.
- Folding `NPCAsset` into `world.npc_services`: would grow that app
  indefinitely; the Companion precedent already established that a
  distinct owned-NPC concept gets its own app.

## Consequences
Any future "class-1 → durable follow-up" mechanic (a similar promotion,
recruitment, or conversion gameplay loop) can reuse the same pattern: model
the trigger as an `NPCServiceOffer` with a `rapport_requirement` +
`eligibility_rule`, and resolve any location-scoped context from the PC's
current room at grant time rather than threading new fields through the
shared interaction session.
