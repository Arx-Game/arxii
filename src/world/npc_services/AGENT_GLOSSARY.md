# NPC services glossary

**NPC ontology (class-1..4 scale — canonical names, ADR-0070):**

**Functionary**:
A **class-1** NPC — abstracted, non-piloted, with no ObjectDB and no `scenes.Persona`. It serves a
room role (enables gameplay loops there: mission-giving, permit approval, mission-reporting, future
services) and is a *placement* of an `NPCRole` in a room, so it carries its own `room` FK (there is no
object from which to derive its location). One role has many Functionary placements (a Builders Guild
Clerk in each hall). Rarely staff-pilotable (a beloved fixture puppeted for a scene); normally unpiloted.
Promotion into a named, owned asset is the Asset/Companion system's job (#672).
_Avoid_: room NPC, giver, class-1 NPC (for the surface term), nameless functionary.

**Standing NPC**:
A **class-2** NPC — a named `scenes.Persona` on an unpuppeted Character object, permanently in a room.
Has persistent `NPCStanding` (per-PC affection). Room comes from its object, not a placement FK.
`NPCStanding` is kept separate from `NpcRegard` (which covers an NPC's opinion of any
persona — PC or NPC — plus Organizations and Societies) — `NPCStanding` is specifically the
PC-persona-vs-NPC-persona offer-eligibility gate; see ADR-0085.
_Avoid_: class-2 NPC, named NPC.

**Story NPC**:
A **class-3/4** NPC — a Character object with a full `CharacterSheet`, intended to be piloted/roleplayed
by staff or GMs for stories.
_Avoid_: class-3 NPC, class-4 NPC, major NPC.

**NPCRole**:
The staff-authored **catalog** entry ("Builders Guild Clerk", "Town Guard") — a bundle of
`NPCServiceOffer` rows. A role is a template, room-less and owner-less; a Functionary is a placement of
one. Not the placement itself.

**NPCServiceOffer**:
One offerable thing on a role, of a `kind` (`OfferKind`: PERMIT, MISSION, …) with a per-kind details
model + effect handler. The single "ask an NPC for a thing" surface, ridden via the `hire` /
`InteractionSession` loop. Building-permit approval is `kind=PERMIT`.

**NpcRegard** — A notable NPC's signed opinion (`-1000`..`1000`) of another
persona (PC or NPC), an Organization, or a Society. General axis: positive is
favor, negative is hostility — there is no separate "enemy" model. Holder is
always a notable NPC's `Persona` (v1; org/society-as-holder is a future
extension of the same discriminator, not built). Deliberately separate from
`NPCStanding` — see that entry's cross-reference and ADR-0085.
_Avoid: "NpcEnmity" (collides with the dead `ThreadAxis.ENMITY`), "grudge" as a
model name (implies negative-only; fine as informal narration of a strongly
negative row)._

**NPC Debt**:
`NPCStanding.debt` (#1718) — generic per-(PC, NPC) debt incurred by drawing more
aid than the PC has currently earned; repays on read as affection/mission
progress grows past the baseline snapshotted when the debt was incurred
(`incur_npc_debt`/`outstanding_debt`, `world.npc_services.services`). Not
Court-specific — any petition-style feature may reuse it.
_Avoid_: favor, boon, obligation (no such terms exist elsewhere in this codebase).

**Petition failure streak**:
`NPCStanding.consecutive_failed_petitions` (#1718) — increments on a failed
petition-style check against this NPC, resets on success
(`record_petition_outcome`). Mirrors `Contract.consecutive_missed`
(`world.currency`). Crossing an authored threshold is the caller's cue to fire
its own escalation consequence — this field only tracks the count.

**Summons**:
An `OfferSummons` (#2050) — a directed-offer primitive that targets a specific
persona with a mission offer. The servant sees it in their journal and can
accept (delegates to `resolve_offer` → `issue_mission`) or decline. Any
`NPCRole` can direct an offer; the Court layer adds its escalation config.
_Avoid_: wish, demand, boon (informal narration only; the model is "summons").

**Refusal streak**:
`NPCStanding.consecutive_refused_summons` (#2050) — increments on decline/expire,
resets on acceptance (`record_summons_refusal`). Mirrors
`consecutive_failed_petitions` — generic per ADR-0085. Crossing
`CourtGrantConfig.summons_refusal_escalation_threshold` fires the master's
escalation pool.

**The master remembers**:
The refusal mechanism (#2050) — declining or letting a summons lapse drops
affection (auto-lowering the Court grant ceiling) and bumps the refusal streak.
Three refusals later, the master's displeasure arrives as authored consequences,
not GM improvisation. Debt is never the price of disobedience.

**TRAIN offer / Academy training** (#2440):
`OfferKind.TRAIN` — an Academy (or Great Archive) trainer teaches a specific
technique for AP + coin + a Golden Hare. One `NPCServiceOffer`/`TrainOfferDetails`
row per teachable technique (a trainer's "curriculum" is its set of MENU offers,
not a single parameterized offer). `NPCRole.teaches_tradition` scopes which
Tradition's *signature* techniques a trainer may teach — shared (Path × Gift)
*pool* techniques are teachable by any Academy trainer regardless of tradition.
The handler (`effects.run_train_offer`) is the second front door onto
`world.magic.services.gift_acquisition.charge_and_learn`, the shared
charge+acquire core `accept_technique_offer` (player-to-player teaching) also
uses — one seam, two front doors, never a forked acquisition path.
_Avoid_: "teaching offer" for TRAIN specifically (that term is
`magic.TechniqueTeachingOffer`, the player-to-player path — a different model
entirely, though both converge on the same acquisition seam).

**Great Archive self-study** (#2440 ruling 5):
The post-Vanishing path for orphaned traditions — TRAIN offers on a "Great
Archive Librarian" `NPCRole` (same Academy `faction_affiliation`, same AP +
coin + Golden Hare cost as any other trainer), visible only to a learner who
holds a quest-completion `Achievement`
(`world.npc_services.seeds.GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG`). The
gate reuses `NPCServiceOffer.eligibility_rule`'s existing `has_achievement`
predicate leaf (`world.predicates.predicates`) — no bespoke FK. Seeded via
`ensure_great_archive_librarian_role()`; the achievement definition exists on
a fresh DB, but granting it to a character is lore-repo quest content, not
this seed's job. _Avoid_: a new `required_achievement` FK — `eligibility_rule`
is already the offer-visibility predicate for every `NPCServiceOffer` kind.

**Recorded Profile** (`RecordedProfile`, #2632):
A profile "written" by an Archive scholar — in fact player-authored prose, paid for as a
PROFILE_RECORDING offer sitting. Completing the write-up sets the character's current
physical description (via `character_sheets.set_physical_description`, THE desc seam) and
archives the text forever with IC-date + Era stamps: desc history, in-world. Persona-scoped.
_Avoid_: desc snapshot, description version (that's `ProfileTextVersion`, which is the
background/personality history — a different surface).

**Styling Offer** (`StylingOfferDetails`, #2632):
A menu-driven NPC restyle: one offer per (cosmetic trait, option) because the interaction
machinery has no free-input channel. Charges the purse, then applies through the same
`change_appearance` seam dyes and PC stylists use.
_Avoid_: makeover request, salon job.

**Reaction Line** (`NPCReactionLine`, #2632):
A banded, data-authored NPC reaction ("Alphonso sees to <name>, admiring them as if they
were a work of art") — per-ROLE defaults with optional per-FUNCTIONARY override sets
(any functionary lines for a metric replace the role's wholesale). Bands select by
highest `band_floor` <= the served character's `ReactionMetric` value (ALLURE first;
metrics resolve via `reactions.METRIC_RESOLVERS` — one function per metric, never
per-NPC code). `<name>` interpolates the presented name. Builders author rows via
`/api/npc-services/reaction-lines/`.
_Avoid_: custom NPC scripts, per-NPC handlers.
