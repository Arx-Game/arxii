# Character Creation App

This app handles the staged character creation flow for Arx II.

## Overview

Character creation is a multi-stage process that guides players through creating a playable character. The flow is:

1. **Origin** - Select starting area (city), which gates heritage options
2. **Heritage** - Special heritage (Sleeper/Misbegotten) or normal → Species → Gender/Pronouns → Age
3. **Lineage** - Family selection (or "Unknown" for special heritage)
4. **Distinctions** - Advantages and disadvantages
5. **Path** - Class/path selection
6. **Gift** - Tradition, Gift + Technique catalog picks, gift resonance, and Anima Check
   stat/skill (renders the `GiftStage` funnel component; #2426 Task 10)
7. **Attributes & Skills** - Primary stat allocation (cap-aware with distinction/species
   bonuses) plus skill point allocation (moved in from Path, #2426 Task 9)
8. **Appearance** - Height, build, form traits (hair/eye color, etc.)
9. **Identity** - Name, description, personality, background
10. **Final Touches** - Goals (optional)
11. **Review** - Final review and submission

## Key Models

### StartingArea
- Selectable origin locations with crest images
- Gates which heritage options, species, and families are available
- Maps to an Evennia room for character starting location
- Access control: all players, trust-required, or staff-only

### Beginnings
- Worldbuilding paths for each starting area (Arx: Caretaker, Sleeper, Misbegotten —
  canonical prose and gates in the lore repo's `beginnings/arx.md`)
- Controls which species are available (allows_all_species or specific species_options)
- Sets whether family is known (family_known=False for Sleeper/Misbegotten)
- Can override starting room (e.g., Sleeper Wake Room)
- Has CG point cost and trust requirements

### OriginTemplate / OriginTemplateSlot (#2478)
- Authored origin-story frames (content models, lore-repo via `CONTENT_MODELS`).
  Multiple templates per Beginning allowed; today one active template auto-assigns.
- `OriginTemplate.frame_narrative` fixes the narrative frame (e.g. "escape from
  Salvation"); `OriginTemplateSlot` carries authored slot prompts the player fills in.
- No slug fields — natural keys from FK + `name` (mirroring `Beginnings`).
- `CharacterOriginSlot` is instance data (FK→`CharacterSheet`, FK→`OriginTemplateSlot`).
- At CG finalize, slot answers are assembled into `Profile.background` prose via
  `assemble_origin_prose()` (pure concatenation, no LLM). The structured rows are
  queryable for future GM/story tools.
- Not required at CG submit (mirrors #2427 Glimpse — no validation gate). Finish-later
  via `OriginStoryEditorDialog` on the character sheet (`set-origin-slot` /
  `clear-origin-slot` sheet API actions).
- `CharacterSheet.origin_story_state` caches NOT_STARTED/SLOTS_ONLY/COMPLETE.

### CGExplanation
- Key-value table: each row has `key`, `text`, and `help_text` fields
- Keys match frontend references (e.g. `origin_heading`, `heritage_intro`)
- All frontend CG copy reads from this model via `useCGExplanations()` hook
- API returns a flat dict: `{key: text, ...}` — frontend type is `Record<string, string>`
- Staff can add new keys directly in admin without migrations
- Seeded via `CG_EXPLANATION_COPY` + `_seed_cg_explanations()` in
  `world/seeds/character_creation.py` (#2162), called from
  `seed_character_creation_dev()` as part of the `character_creation` cluster on
  the Big Button. Each row is upserted with `update_or_create`, so re-running the
  seeder (e.g. after a prose fix in this repo) propagates updated copy to
  already-seeded deploys without clobbering unrelated fields — and staff can still
  hand-edit any row in admin between seeder runs.

### CharacterDraft
- Stores in-progress character creation state
- Tracks current stage and all selections
- Expires after 2 months of account inactivity (staff exempt)
- JSON blob for complex staged data (stats, skills, traits)

## Service Functions

### `finalize_character(draft, add_to_roster=False)`
Creates a Character from a completed draft:
- Resolves starting room (Beginnings override → area default → None)
- Creates Character object via Evennia's create_object
- Creates RosterEntry for roster management
- Handles staff "Add to Roster" vs player submission

### Magic finalization — `finalize_magic_data` (catalog gift/technique contract, #2426)
The magic stage's CG picks are **catalog rows the player selects**, not templates
finalize builds new rows from — `_finalize_gift_and_techniques` only *links* the
chosen `Gift`/`Technique`s to the character; it never creates a `Gift` or `Technique`
row. See `world/magic/services/cg_catalog.py` for the picker endpoints
(`get_gift_options`/`get_technique_options`) and `validators.py:compute_magic_errors`
for the five-branch validation gate this data must satisfy before submission.

- `draft.draft_data["selected_gift_id"]` names the chosen catalog `Gift`.
  `world.magic.specialization.services.grant_gift_to_character(sheet, gift,
  resonance=...)` mints the `CharacterGift` link and provisions the latent level-0
  GIFT thread (#1578, ADR-0055) in one call — the same primitive `grant_path_magic`
  uses for path-crossing grants. No-op (early return, nothing created) when the
  draft has no `selected_gift_id` — only legacy/test-only draft_data reaches this,
  since `compute_magic_errors` requires the key on any draft that reaches submission.
- The resonance is read from `draft.draft_data["selected_gift_resonance_id"]`
  (required by `compute_magic_errors`) and resolved to a `Resonance` row; `None`
  when unset or invalid — `grant_gift_to_character` skips thread provisioning in
  that case (no fallback-to-first-supported-resonance; that fallback only existed
  in the old CG-creates-a-new-technique path).
- `draft.draft_data["selected_technique_ids"]` names the chosen catalog
  `Technique`s (drawn from the gift's pool ∪ the tradition's signature set); each
  gets a `CharacterTechnique.objects.get_or_create` link. `announce_access_change`
  fires once with every linked technique as `gained`.
- **Outcome-flavor consequence-pool selection is dropped entirely** (spec
  correction on #2426) — every catalog technique already carries its own authored
  `action_template`; finalize no longer reads a `selected_consequence_pool_id` key
  or calls `resolve_cast_action_template`. That resolver and
  `InvalidConsequencePoolChoice` remain live for the technique-authoring workbench
  (`world.magic.services.technique_builder`) — only the CG-finalize call site was
  removed.
- CharacterTradition creation is unconditional — `compute_magic_errors` requires
  `selected_tradition` on any draft that reaches submission, so the old
  `if draft.selected_tradition:` guard was dropped.
- **Golden Hare Academy entrance obligation (#2428 Task 3)** —
  `_finalize_academy_entrance_obligation` resolves the "Shroudwatch Academy"
  `Organization` by name (seeded by `world.seeds.character_creation.
  ensure_shroudwatch_academy`) and creates a `societies.OrganizationObligation`:
  `OWED` when `draft.selected_tradition.name == "Unbound"`, else
  `SETTLED_BY_SPONSOR` (`settled_at` stamped, `settled_by_token` left `NULL` —
  the sponsor's Hare is lore-recorded, not minted at CG time). Defensive logged
  skip if the Academy isn't seeded (mirrors `seed_beginning_traditions`'s
  Unbound-tradition skip); `get_or_create`-idempotent.

### `get_accessible_starting_areas(account)`
Returns StartingArea queryset filtered by account access level.

### `can_create_character(account)`
Checks if account can create characters (verified, positive trust, under limit).

## Gender & Pronouns

- Gender stored as CharField with choices: male, female, nonbinary, other
- Pronouns are separate editable fields (subject, object, possessive)
- Default pronouns auto-populated on gender selection
- Players can customize pronouns freely; abuse handled via moderation

## Important Notes

- Starting rooms always resolve to a real room (#2121): a `Beginnings`/`StartingArea`
  override, or `CharacterDraft.get_starting_room()`'s canonical-fallback-room branch
  (logged loudly) — never a silent `location=None` spawn
- Commoner families are created only at final submission to avoid orphaned records
- Staff bypass all access restrictions and limits
- Navigation between stages is free; incomplete stages are highlighted but not blocked
- Submit is blocked until all required stages are complete
