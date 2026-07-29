# NPC Lifecycle — the tier ladder on the sheet-spine

**Apps:** `src/world/npc_services/` (+ `assets`, `tasking`, `roster` seams) ·
**Spec:** issue #2827 · **Since:** 2026-07 · **ADRs:** 0176 (spine), 0070
(ontology classes, unchanged), 0058 (disposition seam, formalized)

One identity climbs (and descends) a ladder of tiers. **The sheet is the
person; personas are faces on the person — identically for PCs and NPCs**
(ADR-0176). Tiers are layers added to and retired from that spine; nothing
is ever hard-deleted, because persona-anchored history (secrets, rapport,
regard, relationships) IS the record.

## The ladder

| Tier | Representation | Entry | Exit |
|---|---|---|---|
| 0 Ambient | room stats only (TRAFFIC bands, staffing profiles) | authored once | — |
| 1 Instantiated | Functionary placement + persona link + sheet + NPC-roster shelf | engagement (auto) or staff | soft-retire placement |
| 2 Attached | + NPCAsset claims, personality, aptitudes | cultivation/coercion/charm/flip | dismiss/lose asset |
| 3 Standing | + body object placed in room | staff (candidates queue) | `demote_to_instantiated` |
| 4 Story | + piloted play (ADR-0071 protection) | staff/GM | staff |
| 5 Rostered | shelf entry moved to AVAILABLE roster | staff (`graduate_to_roster`) | normal roster lifecycle |

## Phase 1 — venue auto-staffing (`staffing.py`)

`StaffingProfile` (1:1 with `buildings.BuildingKind`) + `StaffingProfileLine`
(role slots). `complete_building_activation` applies the profile to the
building's entry room (the Town Crier feature-placement pattern,
generalized); the weekly `staffing.weekly_refill` cron re-ensures slots — a
vacated slot resets to a fresh faceless hire (active, no name, no persona).
Staff curation happens at the *profile* level: prune the line, or the sweep
re-staffs it. One active placement per (role, room) — a line is a slot, not
a headcount. Staff CRUD: `/api/npc-services/staffing-profiles|staffing-lines/`.

## Phase 2 — instantiate-on-engagement (`instantiation.py`)

`Functionary.persona` (nullable FK) is the materialization link.
`materialize_functionary` mints Character + CharacterSheet + PRIMARY persona
(`create_character_with_sheet` — the same call promotion uses), a generated
name, a shelf entry on the never-claimable NPC roster (`RosterType.NPC`),
and rolls personality quirks. The hook lives in `npc_start`
(`StartNPCInteractionAction`) — the seam telnet `hire` and the web
interaction viewset converge on — so engaging a faceless co-located
placement makes it real automatically, and rapport flows into durable
`NPCStanding` from the first conversation (ADR-0058's seam, formalized).

**Name cultures**: `NameCulture` + weighted `NameCultureEntry` pools
(GIVEN/SURNAME), resolved by nearest area ancestor (`AreaClosure` walk) with
a global default fallback; `generate_person_name(culture, family=...)` uses
`Family.name` as the surname for on-demand faceless nobility. Unseeded
shards fall back to a PLACEHOLDER given name — instantiation never blocks
on content.

## Phase 3 — dual-mode recruitment (`assets`)

Promotion is **in-place by default**: `_promote_functionary` materializes
the placement's identity (reusing an existing persona — never a duplicate
mint) and creates the `NPCAsset` claim; the NPC keeps working the venue,
which keeps the listener flip/counterplay ecology alive. **Extraction**
("quit and come with me") is the separate `extract_asset` service +
`/api/assets/{id}/extract/`: retires every active placement carrying the
persona; the venue slot refills on the weekly sweep; the identity is
untouched. (Reverses the pre-#2827 promotion-consumes-the-functionary
behavior; the dedup guard re-keys on NPCAsset rows.)

## Phase 4 — personality + aptitudes

`PersonalityTrait` (authored vocabulary; optional `eased_check` +
magnitude) and per-persona `NpcPreference` likes/dislikes, rolled at
materialization. `preference_modifier(npc_persona, check_type)` eases or
hardens rolls *against* the NPC — consumed by cultivation offers and
counterplay suppress/flip. `tasking.NpcTaskAptitude` bands (lazily minted,
staff-editable) feed dispatch resolution and listener tradecraft rolls at
`APTITUDE_STEP` per band.

## Phase 5 — ladder lifecycle (`lifecycle.py`)

`promote_to_standing` (body into room, background slot retires),
`demote_to_instantiated` (body unplaced, named placement returns),
`standing_candidates` (earned prominence = active asset claims; a staff
review queue, never automatic), `graduate_to_roster` (shelf entry →
AVAILABLE roster, `previous_roster` stamped, history rides along —
`available_characters()` immediately sees it). Staff surfaces:
`/api/npc-services/lifecycle/…`.

## Deliberately not here

Tier-0 *consumers* (mob formation, stealth publicness, venue economics) are
future specs against the existing ambient stat cascade. Combat opposition
stays sheet-less per ADR-0038 — the ladder is about social NPCs.
