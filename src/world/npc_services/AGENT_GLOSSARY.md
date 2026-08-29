# NPC services glossary

**NPC ontology (class-1..4 scale — canonical names, ADR-0070):**

**Functionary**:
A **class-1** NPC — abstracted, non-piloted, with no ObjectDB and no `scenes.Persona`. It serves a
room role (enables gameplay loops there: mission-giving, permit approval, mission-reporting, future
services) and is a *placement* of an `NPCRole` in a room, so it carries its own `room` FK (there is no
object from which to derive its location). One role has many Functionary placements (a Builders Guild
Clerk in each hall). Rarely staff-pilotable (a beloved fixture puppeted for a scene); normally unpiloted.
Promotion into a named, owned asset is the Asset/Companion system's job (#672). On web (#3044), every
active Functionary in the current room surfaces via the room-state payload's `npc_givers` field
(`role_id` + display name — a Functionary carries no `ObjectDB`, so it can never appear in the
`characters`/`objects` room-occupant lists); `NpcGiversBlock`
(`frontend/src/game/components/room-panel/NpcGiversBlock.tsx`) offers a "Talk" button per giver that
mounts the existing `NPCInteractionDialog`.
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

**Statline Preset** (`NPCStatlinePreset`, #3427):
A staff-authored curated archetype ("Guard", "Courtier") a GM selects — never edits — at Story NPC
mint time, giving the NPC real, rollable `CharacterTraitValue`/`CharacterSkillValue` rows instead of
a blank sheet. Lives in `world.roster.models` (beside `mint_story_npc`), not here — the NPC ladder
above is unrelated (Story NPC statting is a mint-time convenience, not a rung on it). Applies once;
no re-apply path — a second application invites drift, so staff hand-adjust an existing NPC's values
via admin instead.
_Avoid_: template (already means `NPCRole`/`ItemTemplate` elsewhere), stat block (D&D-coded).

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

## Tier ladder (#2827)

- **Sheet-spine** — the identity rule (ADR-0176): the CharacterSheet is the
  person; personas are faces. NPC tiers are layers on the spine.
- **Materialize / instantiate** — mint a faceless placement's identity
  (sheet + PRIMARY persona + generated name + NPC-roster shelf entry).
  Happens automatically at first engagement (`npc_start`). _Avoid_:
  "spawn" (creates bodies, not identities).
- **Staffing profile / slot** — a BuildingKind's baseline crew; a line is a
  (role, room) slot, not a headcount. Vacated slots refill weekly with a
  fresh faceless hire.
- **Name culture** — an area/society-keyed weighted name pool; Family.name
  supplies noble surnames.
- **In-place recruitment vs extraction** — promotion keeps the NPC on the
  job (default); `extract_asset` is the "quit and come with me" choice.
- **Standing candidate** — an NPC persona with enough active asset claims
  to surface in the staff review queue for a body. Never auto-promoted.
- **Graduation / rostering door** — moving the NPC shelf entry to the
  claimable AVAILABLE roster; the persona's history rides along.
- **Melt back / retire to the ether** — layer retirement (placement
  inactive, body unplaced). Never deletion; history keeps the identity
  resurrectable.

## Household daily-life behaviors (#2989)

- **Doorman announcement** — a deterministic room echo naming every arrival
  when a room has an active DOORMAN `NPCAssignment`; no check, no gate on
  owner/tenant standing. Distinct from "access challenge" (turning away the
  unwanted), which stays deferred pending a real invitation/guest-list
  primitive. _Avoid_: door guard, access control (neither exists here).
- **Servant ambience** — the pampering pair (`prepare_meal`/`prepare_bath`,
  `world.npc_services.servant_ambience`): same delay+departure/arrival-echo
  shape as servant fetch. Meal is pure ambience (no mechanical payoff — no
  ordinary-meal hunger system exists to hook); bath additionally carries a
  small gated fatigue recovery through the existing `recover_fatigue` seam.
  _Avoid_: household provisioning, meal system (neither is built — this is
  ambience only).
- **Expulsion bar** — the unresistable OOC soft gate (`ExpulsionBar` model):
  a room owner shows a disruptive character out and bars their re-entry, no
  check, no roll, ever. Authorization is owner-only
  (`IsRoomOwnerPrerequisite`); a posted SERVANT/DOORMAN NPC is narration
  only — the room echo names them as the one physically escorting the
  target when one is on duty, but they never independently trigger or
  authorize the expulsion. A consent/disruption valve, not a combat
  surface — distinct from guard detection (a rolled, resistible stealth
  check) and from the deferred doorman access-challenge. Entry enforcement
  is pre-traversal (`check_exit_traversal`, portal travel, and `home`), not
  post-arrival. _Avoid_: kick, ban, eviction (this bars re-entry to one
  room, not an account- or building-wide action).
