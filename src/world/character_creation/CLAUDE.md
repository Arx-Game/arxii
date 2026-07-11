# Character Creation App

This app handles the staged character creation flow for Arx II.

## Overview

Character creation is a multi-stage process that guides players through creating a playable character. The flow is:

1. **Origin** - Select starting area (city), which gates heritage options
2. **Heritage** - Special heritage (Sleeper/Misbegotten) or normal → Species → Gender/Pronouns → Age
3. **Lineage** - Family selection (or "Unknown" for special heritage)
4. **Distinctions** - Advantages and disadvantages
5. **Path & Skills** - Class/path selection and skill customization
6. **Attributes** - Primary stat allocation (cap-aware with distinction/species bonuses)
7. **Magic** - Cantrip selection, optional facet, aura distribution
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
- Worldbuilding paths for each starting area (e.g., Sleeper, Normal Upbringing, Noble Birth)
- Controls which species are available (allows_all_species or specific species_options)
- Sets whether family is known (family_known=False for Sleeper/Misbegotten)
- Can override starting room (e.g., Sleeper Wake Room)
- Has CG point cost and trust requirements

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

### Magic finalization — `finalize_magic_data`
After `CharacterGift` is created for the chosen gift, the magic stage provisions the
latent GIFT thread (#1578, ADR-0055):
- `provision_latent_gift_thread(sheet, gift, resonance=...)` creates the level-0 GIFT
  thread (the specialization substrate), idempotent on `(owner, gift)` and write-once on
  resonance. One active GIFT thread per gift.
- The resonance is read from `draft.draft_data["selected_gift_resonance_id"]`. The
  frontend CG resonance picker is built (#1620): the `CantripSelector` component
  renders a resonance dropdown (via `useResonances()`) that writes this key, and
  `compute_magic_errors` requires it — submission is blocked until a resonance is
  selected. When unset (legacy drafts), the provisioning falls back to
  `gift.resonances.first()` with a warning, and skips entirely if the gift
  supports no resonances.
- The cantrip's starting technique may also carry a chosen consequence-pool "flavor"
  (#1320): `draft.draft_data["selected_consequence_pool_id"]` is read and resolved via
  `world.magic.services.technique_builder.resolve_cast_action_template()` to pick the
  `Technique.action_template`. The frontend picker (CG magic stage's
  `CantripSelector`) is built and writes this key. An unset key resolves
  to the shared default template (`resolve_cast_action_template(None)`); a stale/invalid
  id raises `InvalidConsequencePoolChoice`, which finalize catches, logs a warning, and
  falls back to the shared default template — finalize never fails on a bad pool id.

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
