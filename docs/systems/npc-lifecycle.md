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

## GM story-NPC on-ramp (#3426) — parallel to the ladder, not a rung on it

A GM prepping a session's cast doesn't climb the ladder above — that's for
*ambient* NPCs discovered through play (Functionary engagement, promotion,
extraction). A **Story NPC** is authored directly by a trust-tiered GM and
is playable immediately, with no Functionary placement in the chain:

- **Lightweight mint** — `mint_story_npc` (`world/roster/services/staff_characters.py`)
  gates on `GMProfile` at JUNIOR+ (staff bypass) and
  `GMLevelCap.max_story_npcs` (per-GM-level cap, most-restrictive/refuse when
  no cap row exists), then delegates to `mint_staff_character`'s working set:
  Character + `CharacterSheet` + PRIMARY `Persona` + a `RosterEntry` on the
  NPC shelf (`RosterType.NPC`) + an active `RosterTenure` binding it to the
  GM's own account. `description`, when given, writes
  `CharacterSheet.additional_desc` via `set_physical_description`. Telnet:
  `gm npc <name>[=<description>]` (`CmdGMDashboard`, `commands/gm_ops.py`);
  Action: `mint_story_npc` (`actions/definitions/gm_npcs.py`).
- **Heavyweight claim** — `finalize_gm_character(draft, claim_as_npc=True)`
  (`world/character_creation/services.py`) is the full-CG sibling: a GM runs
  a character through CG as normal, then claims the finished sheet as their
  own NPC at finalize time instead of landing it tenure-less on Available.
  Same JUNIOR+/cap authorization (`check_story_npc_cap`, shared with
  `mint_story_npc`). Web: `CharacterDraftViewSet.finalize_gm`'s
  `claim_as_npc` body flag + `FinalizeForTableDialog`'s "This is my NPC, not
  an appable character" checkbox.
- Either way, the tenure is what makes it playable: the persona picker
  (`get_account_personas`) and telnet `@ic` key on `RosterTenure`, not on
  any ladder tier — a Story NPC is immediately speakable/emotable/actable in
  a scene, the same as a PC.
- The NPC shelf is never publicly listed (`RosterEntryViewSet` excludes
  `RosterType.NPC` entries from the general/anonymous queryset — staff and
  the tenure holder still see them) — an unrevealed story's cast doesn't
  leak through roster browsing.
- **Exit is staff-only today** (deliberate deferral): there is no
  self-service release/retire action to free a cap slot — staff ends the
  `RosterTenure` in Django admin. A self-service release is a stated
  follow-up, not an oversight.

## Story-NPC statline presets (#3427)

A minted Story NPC used to have a blank sheet — a GM's only path to a real,
rollable statline was to hand-invent trait/skill values. Presets close that
gap with a **curated archetype catalog**: staff author the presets in admin;
GMs select at mint time, never invent values (ADR-0176 stays intact — the
applied values land as the same real `CharacterTraitValue`/
`CharacterSkillValue` rows a PC's sheet carries).

- **Models** (`world.roster.models.npc_presets`): `NPCStatlinePreset`
  (`name` unique, `description`, `NaturalKeyMixin + CreditedContent +
  SharedMemoryModel`, registered in `CONTENT_MODELS`) with child rows
  `NPCPresetTraitLine` (`trait` FK PROTECT to a STAT `Trait`, `display_value`
  1-10) and `NPCPresetSkillLine` (`skill` FK PROTECT, `value` true 1-100),
  each unique per (preset, trait)/(preset, skill). Admin: one preset page
  with two `TabularInline`s. The child-line models are not themselves in
  `CONTENT_MODELS` (mirrors `traits.TraitRankDescription`'s asymmetry) — they
  ride along with their preset's export/import via the FK, and the starter
  catalog's own lines are seeded unconditionally once their preset exists.
- **Service** `apply_npc_preset(sheet, preset)`
  (`world.roster.services.staff_characters`, beside `mint_story_npc`) mirrors
  CG finalize's write shape exactly — `_create_stat_values`/
  `_create_skill_values` in `world.character_creation.services` — rather
  than calling those private draft-dict helpers: trait lines write a
  `CharacterTraitValue` at `display_value * STAT_DISPLAY_DIVISOR`; skill
  lines write a `CharacterSkillValue` plus the #2894 bridging
  `CharacterTraitValue` on `skill.trait` (the check engine reads only trait
  rows); every written value gets a `CharacterTraitChange` provenance stamp
  (`old_value=0`, `source=TraitChangeSource.NPC_PRESET`). Refuses a sheet
  that already carries any NPC_PRESET-sourced stamp — no re-apply path in
  v1 (a second application path invites drift); staff adjust an existing
  NPC's values via admin instead.
- **Wiring:** `mint_story_npc` gains a keyword-only `preset:
  NPCStatlinePreset | None = None`; `MintStoryNPCAction` gains an optional
  `preset` kwarg, resolved by natural key inside the Action (an unknown name
  refuses the whole mint — no partial mint with a silently-dropped preset).
  Telnet: `gm npc <name>[=<description>] [preset=<name>]` (`CmdGMDashboard`,
  `commands/gm_ops.py`) — `preset=` is pulled off the tail before the
  existing `<name>[=<description>]` split runs, so it composes with a
  description.
- **API:** `NPCStatlinePresetViewSet` (`/api/roster/npc-presets/`,
  read-only, `IsGMOrStaff`, `SearchFilter` on `name`, standard pagination)
  feeds a preset `Select` in the #3426 mint dialog (`GMDashboardPage`).
- **Seed:** 3-4 starter presets (Guard, Courtier, Innkeeper, Investigator)
  via `authored_or_sample` (ADR-0168) in the roster seed cluster
  (`world.roster.seeds.ensure_starter_npc_presets`, called from
  `world.seeds.clusters._seed_roster`) — modest values, staff rewrite
  freely. A line whose named Trait/Skill isn't itself authored yet is
  skipped, not invented.
- **Cross-GM preset library** (a shared/reusable preset catalog visible
  across every GM) was considered at spec review and closed as premature —
  the #3426 "My NPCs" list already covers self-reuse and #2001's custody
  system already protects story assets; revisit if multiple GMs start
  running recurring casts that would benefit from sharing presets.

## Deliberately not here

Tier-0 *consumers* (mob formation, stealth publicness, venue economics) are
future specs against the existing ambient stat cascade. Combat opposition
stays sheet-less per ADR-0038 — the ladder is about social NPCs.
