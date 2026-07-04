# The offer→staked-beat link lives on MissionOfferDetails, not NPCServiceOffer

**Decision:** the FK that lets an NPC mission offer resolve a staked story beat is
`MissionOfferDetails.source_beat` (nullable FK → `stories.Beat`, `SET_NULL`) — not a field on the
unified `NPCServiceOffer`, and not a new field on `MissionTemplate`.

**Context:** the #1770-PR4 stakes opt-in chain (`activate_stakes_for_instance`,
`MissionRiskAcknowledgement`, `on_mission_complete_for_beat`) was fully built end-to-end for
missions but sat dormant for every offer-accepted run, because nothing on the offer path ever
populated `MissionInstance.source_beat` — only trigger-based / staff-seeded runs could set it
directly. `issue_mission` (`world.missions.services.offer_handler`) now copies
`MissionOfferDetails.source_beat` onto the new `MissionInstance` at accept, which arms the chain:
`activate_stakes_for_instance` locks the beat's stakes contract at acceptance,
`_require_risk_acknowledgement` now also gates when the linked beat is staked
(`risk != RenownRisk.NONE`) and surfaces the beat's `player_summary` stake lines in the
acknowledgement error, and `on_mission_complete_for_beat` completes the beat at the run's terminal
route.

**Rationale:** ADR-0010 (FK direction is specific→general — the link lives on the more
specific/dependent side, pointing at the reusable primitive, never the reverse).
`MissionOfferDetails` is the mission-specific detail row hung off `NPCServiceOffer`; the beat link
is mission-specific data (what beat *this* offer resolves) and has no meaning for the other kinds
`NPCServiceOffer` fronts (training, rumor). Putting it on `NPCServiceOffer` itself would mean every
non-mission offer row carries a column it can never use. `MissionOfferDetailsSerializer` exposes
the field for staff authoring.

**Independence:** `Beat.required_mission` (`stories`, FK → `MissionTemplate`, Phase-5b.3 stub —
the engine that would walk it to auto-spawn or require a specific mission run is still deferred)
and `MissionOfferDetails.source_beat` are deliberately independent. No runtime path reads
`required_mission` today, so there is nothing to keep in sync and no cross-FK `clean()` guard is
added — a `MissionOfferDetails` row is free to name a `source_beat` regardless of what (if
anything) that beat's `required_mission` points at. Wiring the two together is a separate,
unbuilt design question, not a consistency bug.

**Rejected:** (a) FK on `NPCServiceOffer` — dead weight on every training/rumor offer row, and
the wrong side of the ADR-0010 specific→general split. (b) FK on `MissionTemplate` — a template is
repeatable across many offers and personas; anchoring the beat there would force every offer
issued from that template to feed the same one beat, when in practice a given template can be
handed out generically with no beat attached, or reused later for a different beat. (c)
beat-spawns-offer (the beat creates/targets its own offer rather than an offer naming a beat) —
there is no offer-creation service today for a beat to call into; building one is a materially
larger change than adding one nullable FK plus a copy-on-issue step, for no behavior this issue
needs.

> Status: accepted · Source: #1780; builds on the #1770-PR4 stakes chain (ADR-0067, ADR-0076,
> ADR-0077, ADR-0078) and ADR-0010 (FK direction).
