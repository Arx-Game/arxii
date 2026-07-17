# Character Creation System

Multi-stage character creation flow with draft persistence, CG point budgets, catalog gift/technique magic selection, and staff review workflow.

**Source:** `src/world/character_creation/`
**API Base:** `/api/character-creation/`

---

## Enums (constants.py)

```python
from world.character_creation.constants import (
    Stage,                    # ORIGIN(1) through REVIEW(11)
    StartingAreaAccessLevel,  # ALL, TRUST_REQUIRED, STAFF_ONLY
    ApplicationStatus,        # SUBMITTED, IN_REVIEW, REVISIONS_REQUESTED, APPROVED, DENIED, WITHDRAWN
    CommentType,              # MESSAGE, STATUS_CHANGE
)
```

## Types (types.py)

```python
from world.character_creation.types import (
    StatAdjustment,      # TypedDict: stat, old_display, new_display, reason
    ResonanceSource,     # Dataclass: distinction_name, value
    ProjectedResonance,  # Dataclass: resonance_id, resonance_name, total, sources
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CGPointBudget` | Global CG point budget config | `name`, `starting_points`, `is_active`, `xp_conversion_rate` |
| `StartingArea` | Selectable origin locations | `name`, `realm` (FK), `description`, `crest_image`, `default_starting_room`, `is_active`, `sort_order`, `access_level`, `minimum_trust` |
| `Beginnings` | Worldbuilding paths per area | `name`, `starting_area` (FK), `description`, `family_known`, `allowed_species` (M2M), `starting_languages` (M2M), `societies` (M2M), `traditions` (M2M via `BeginningTradition`), `cg_point_cost`, `social_rank` |

**Content vs seeds:** the real, authored `Beginnings` rows (e.g. the Arx trio —
Caretaker/Sleeper/Misbegotten) are **lore-repo content fixtures**
(`fixtures/character_creation/beginnings.json` + `beginningtradition.json`,
prose + rulings in the lore repo's `beginnings/arx.md`), loaded by
`load_world_content` (natural-key upserts — the fixture also retires the
seeded placeholders via `is_active: false` rows) and exported back by
`content_export` (`Beginnings`/`CGExplanation` are in `CONTENT_MODELS`). The
rows seeded below are generic bootstrap placeholders only; real content never
expands seed data in this public repo (TehomCD ruling, 2026-07-17).

### Template/Configuration Tables

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `BeginningTradition` | Maps traditions to beginnings with optional required distinction | `beginning`, `tradition`, `required_distinction`, `sort_order` |

### Draft State (models.Model - per-player)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterDraft` | In-progress creation state | `account`, `current_stage`, `selected_area`, `selected_beginnings`, `selected_species`, `selected_gender`, `age`, `family`, `family_member`, `selected_path`, `selected_tradition`, `height_band`, `height_inches`, `build`, `draft_data` (JSON) |

**Note:** Magic selections during CG (gift, techniques, gift resonance, Anima Check stat/skill, aura distribution) are stored in `draft_data` JSON, not in separate Draft* models. The old DraftGift, DraftTechnique, DraftMotif, DraftMotifResonance, DraftMotifResonanceAssociation, DraftAnimaRitual, TraditionTemplate, TraditionTemplateTechnique, and TraditionTemplateFacet models have been removed.

### Application/Review

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DraftApplication` | Review lifecycle for a draft | `draft` (OneToOne), `status`, `submitted_at`, `reviewer`, `reviewed_at`, `submission_notes`, `expires_at` |
| `DraftApplicationComment` | Comment or status change event | `application`, `author`, `text`, `comment_type`, `created_at` |

---

## CG Stages

| # | Stage | Completion Criteria |
|---|-------|-------------------|
| 1 | Origin | `selected_area` is set |
| 2 | Heritage | Beginnings, species, gender selected; family/tarot complete; CG points >= 0; species allowed by beginnings |
| 3 | Lineage | Family selected, OR familyless with tarot card |
| 4 | Distinctions | `traits_complete` flag set; CG points >= 0 |
| 5 | Path | Path selected (`get_path_errors`) |
| 6 | Gift | Tradition, gift, >=1 technique(s), gift resonance, and Anima Check stat/skill all selected and valid (`compute_magic_errors`, 5-branch return-first gate); renders the `GiftStage` funnel component (#2426 Task 10) |
| 7 | Attributes & Skills | All 12 primary stats present, valid range (1-5), points remaining = 0; skill point allocation validated against budget (moved in from Path, #2426 Task 9) |
| 8 | Appearance | Age, height band, height inches, build all set |
| 9 | Identity | `first_name` in draft_data |
| 10 | Final Touches | Always complete (goals are optional) |
| 11 | Review | Never "complete" -- final submission step |

---

## Key Methods

### CGPointBudget

```python
from world.character_creation.models import CGPointBudget

CGPointBudget.get_active_budget()          # Returns int (default 100)
CGPointBudget.get_active_conversion_rate() # Returns int (default 2 XP per CG point)
```

### CharacterDraft

```python
from world.character_creation.models import CharacterDraft

draft.is_expired                        # True if > 60 days inactive (staff exempt)
draft.get_starting_room()               # Beginnings override -> area default -> canonical
                                         # fallback room (logged loudly) -> None (#2121);
                                         # see world.seeds.character_creation.
                                         # ensure_canonical_fallback_room
draft.get_stage_completion()            # Dict[int, bool] for all stages
draft.can_submit()                      # True if all stages (except Review) complete
draft.calculate_cg_points_remaining()   # starting_budget - total_spent
draft.calculate_cg_points_breakdown()   # itemized [{category, item, cost}, ...]:
                                         # "heritage" (Beginnings.cg_point_cost),
                                         # "distinction" (per draft_data distinction),
                                         # "species" (SpeciesGiftGrant.cg_point_cost summed
                                         # across the selected species + ancestors —
                                         # see docs/systems/species.md)
draft.calculate_final_stats()           # Dict[str, int] with bonuses applied
draft.enforce_stat_caps()               # Clamp stats after distinction changes
draft.get_expected_gift_count()         # Base 1 + bonus from distinctions
```

### DraftApplication

```python
from world.character_creation.models import DraftApplication

application.is_locked     # True when submitted or in_review
application.is_terminal   # True when approved, denied, or withdrawn
application.is_editable   # True when revisions_requested
```

---

## Service Functions

```python
from world.character_creation.services import (
    finalize_character,           # Create Character from completed draft (atomic); stamps
                                  #   RosterEntry provenance (STAFF if add_to_roster else
                                  #   PLAYER) + created_by_account (#1506)
    finalize_gm_character,        # GM path: full character + Available RosterEntry (GM_TABLE
                                  #   provenance + created_for_table) + Story/StoryParticipation
    get_accessible_starting_areas,# Filter areas by account access
    can_create_character,         # Check eligibility (trust, limits)
    submit_draft_for_review,      # Create DraftApplication in SUBMITTED
    unsubmit_draft,               # Return to REVISIONS_REQUESTED
    resubmit_draft,               # Re-submit after revisions
    withdraw_draft,               # Withdraw with soft-delete expiry
    claim_application,            # Staff: claim for IN_REVIEW
    approve_application,          # Staff: approve and finalize (atomic)
    request_revisions,            # Staff: send back with feedback
    deny_application,             # Staff: deny with 14-day soft-delete
    add_application_comment,      # Add message to thread
    finalize_magic_data,          # Link the draft's chosen catalog Gift/Techniques to the character
)
```

`finalize_magic_data` also creates the CG-finalize Golden Hare Academy obligation
row (#2428 Task 3, `_finalize_academy_entrance_obligation`): resolves the
"Shroudwatch Academy" `Organization` by name (seeded by
`world.seeds.character_creation.ensure_shroudwatch_academy`) and creates an
`OWED` `OrganizationObligation` when `draft.selected_tradition.name == "Unbound"`,
else a `SETTLED_BY_SPONSOR` row (`settled_at` stamped, `settled_by_token` left
`NULL` — the sponsor's Hare is lore-recorded, not minted at CG time). Defensive
logged skip if the Academy isn't seeded. See `docs/systems/societies.md`'s
Obligations section for the model/service detail.

---

## Email Notifications (#2162)

`world.character_creation.email_service.CGEmailService` sends plain-text notifications at every
review-state transition, called (best-effort, exceptions logged not raised) from the corresponding
service function:

- `handle_submission` — confirmation to the applicant + notification to staff; called from
  `submit_draft_for_review`
- `send_application_approved` — called from `approve_application`
- `send_revisions_requested` — called from `request_revisions`
- `send_application_denied` — called from `deny_application`

`CGEmailService` extends `world.roster.email_service.EmailServiceBase` (not `RosterEmailService`
itself) — `EmailServiceBase` was split out of `RosterEmailService` in the same change so sibling
domain services can reuse `_send_email`/`_get_staff_emails` without subclassing a service whose
`send_application_approved`/`send_application_denied` take a roster-specific `tenure` arg CG
applications don't have (subclassing would have meant a narrower override, an LSP violation caught
by `ty`'s `invalid-method-override`). The applicant's email comes from `DraftApplication.player_account`
(survives draft deletion); `_character_name` falls back to the draft's staged first name before
`character_name` is populated at approval.

---

## API Endpoints

### Lookup Data
- `GET /api/character-creation/starting-areas/` - Starting areas filtered by access level
- `GET /api/character-creation/beginnings/` - Beginnings filtered by `starting_area` and trust
- `GET /api/character-creation/species/` - Species with parent hierarchy
- `GET /api/character-creation/families/` - Playable families, filterable by `area_id`
- `GET /api/character-creation/genders/` - Gender options
- `GET /api/character-creation/pronouns/` - Pronoun sets
- `GET /api/character-creation/cg-budgets/` - Active CG point budget
- `GET /api/character-creation/paths/` - Active Prospect-stage paths
- `GET /api/character-creation/traditions/?beginning_id=X` - Traditions for a beginning
- `GET /api/character-creation/tarot-cards/` - Tarot cards for naming ritual
- `GET /api/character-creation/form-options/{species_id}/` - Form traits for a species
- `GET /api/character-creation/can-create/` - Eligibility check

### Draft Management
- `GET/POST /api/character-creation/drafts/` - List/create drafts
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Read/update/delete draft
- `GET /api/character-creation/drafts/{id}/cg-points/` - CG points breakdown
- `POST /api/character-creation/drafts/{id}/select-tradition/` - Select/clear tradition
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Staff: finalize directly to roster (STAFF provenance)
- `POST /api/character-creation/drafts/{id}/finalize-gm/` - Player-GM: finalize onto the Available roster for a table they own (GM_TABLE provenance; body `target_table`, `story_title`, optional `story_description`) (#1506)

### Magic (Gift/Technique Selection, #2426)
- `GET /api/character-creation/gifts/?draft_id=X` - List gifts pickable for the draft's chosen tradition + path
- `GET /api/character-creation/technique-options/?draft_id=X&gift_id=Y` - List technique options (pool ∪ signature) for the chosen gift
- Magic selections (`selected_gift_id`, `selected_technique_ids`, `selected_gift_resonance_id`,
  `anima_check_stat_id`, `anima_check_skill_id`, `anima_ritual_name`, `motif_description`,
  `glimpse_story`) are stored in `draft_data` JSON via draft PATCH — see `GiftStage` (frontend)
  and `compute_magic_errors` (validation)

### Application Workflow (Player)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/unsubmit/` - Un-submit to resume editing
- `POST /api/character-creation/drafts/{id}/resubmit/` - Resubmit after revisions
- `POST /api/character-creation/drafts/{id}/withdraw/` - Withdraw application
- `GET /api/character-creation/drafts/{id}/application/` - Get application with thread
- `POST /api/character-creation/drafts/{id}/application/comments/` - Add comment

### Staff Review
- `GET /api/character-creation/applications/` - List all applications (filterable by status)
- `GET /api/character-creation/applications/{id}/` - Application detail with thread
- `POST /api/character-creation/applications/{id}/claim/` - Claim for review
- `POST /api/character-creation/applications/{id}/approve/` - Approve
- `POST /api/character-creation/applications/{id}/request-revisions/` - Request revisions
- `POST /api/character-creation/applications/{id}/deny/` - Deny
- `POST /api/character-creation/applications/{id}/comments/` - Staff comment
- `GET /api/character-creation/applications/pending-count/` - Pending count

### Staff-Only
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Bypass review, add to roster

---

## Admin

Registered admin classes: `StartingAreaAdmin`, `BeginningsAdmin` (with `BeginningTraditionInline`), `CharacterDraftAdmin` (stage tracking and JSON draft data), `DraftApplicationAdmin` (review status with `DraftApplicationCommentInline`). CGPointBudget is not registered in admin.

## Seeded content + Game Setup hub

A fresh dev DB has no CG-"world" content (Realm/StartingArea/Beginnings/Species/Gender/TarotCard/HeightBand/Build/stats/Rosters/Path), so `finalize_character` cannot run. The `"character_creation"` cluster fixes this:

```python
from world.seeds.character_creation import seed_character_creation_dev
# also runs as part of seed_dev_database() (the "Load sane defaults" Big Button)
seed_character_creation_dev()  # idempotent: get_or_create, never overwrites edits
```

It seeds: `Realm` "Arx"; `StartingArea` "Arx City" (access_level=ALL); `Beginnings` "Commoner" (+ allowed_species M2M); `Species` "Human"; `Gender` key `unspecified`; `TarotCard` "The Fool" (MAJOR, rank 0); `HeightBand` `average_band` + `Build` `average_build`; the 12 stat `Trait` rows; the two `Roster` rows ("Available"/"Active Characters"); a `Path` "The Wanderer" (PROSPECT); and, via `_seed_cg_explanations()` (#2162), every `CGExplanation` heading/intro/desc row (`CG_EXPLANATION_COPY`, 28 keys — one per `copy?.<key>` lookup across the 11 stage components) so a fresh deploy never ships blank CG stage copy. Unlike the rest of this seeder, `CGExplanation` rows are `update_or_create`d on every run (in-repo prose fixes keep reaching already-seeded deploys); every other row stays `get_or_create` (never overwrites a staff edit). `seed_beginning_traditions()` (#2426 whole-branch-review fix) then links every seeded `Beginnings` row to the magic-seeded "Unbound" `Tradition` via a `BeginningTradition` row (`required_distinction=None`) — without it, `TraditionViewSet` and `select_tradition` have nothing to offer and CG's Tradition step is uncompletable on a fresh DB, even the tradition-agnostic Unbound path. `ensure_shroudwatch_academy()` (#2428 Task 3) then seeds the "Shroudwatch Academy" `Organization` (`tradition=None` — deliberate NULL, #2426 ruling; `org_type` "guild"; description/rank titles PLACEHOLDER and content-overridable) that `finalize_magic_data`'s Golden Hare hook resolves by name. `ensure_orphaned_tradition_distinction()` and `seed_metallic_order_tradition()` (#2428 Task 5) then seed the "Orphaned Tradition" drawback `Distinction` (slug `orphaned-tradition`, cost −2, no `DistinctionEffect` — its teeth are trainerlessness, #2440) and the "Metallic Order" example orphaned tradition (starter-gift `TraditionGiftGrant` rows mirroring Unbound's; `BeginningTradition` rows for Arx-realm Beginnings only, each with `required_distinction=orphaned-tradition` — the story-mutable shape staff edit when a recovery quest restores its teachers). Registered last in `CLUSTER_SEEDERS` (after `magic`, which provides the gift/technique/resonance `finalize_character` picks and the Unbound `Tradition` row itself). Verified by `test_playable_slice.py::TestSeededCharacterCreation` (finalize + the real Tradition-step gates run on a seeded-only DB), `test_character_creation_magic_seed.py` (`seed_beginning_traditions` idempotency + defensive skip, `EnsureOrphanedTraditionDistinctionTests`, `SeedMetallicOrderTraditionTests`), `test_traditions.py::OrphanedTraditionSelectionTests` (the drawback gate through the real select-tradition endpoint), `test_idempotency.py::test_edited_cg_row_survives_reseed`, and `test_clusters.py::test_cg_explanations_seeded_and_nonempty`.

The admin **Game Setup** hub (`admin_game_setup` view, `_game_setup/` URL) is a superuser-only landing page for clone hosts: the clone→seed→tweak→export flow, a per-cluster content inventory (via `seeded_models_by_cluster()`) with live row counts, and links to the Big Button, Export/Import, and the World authoring apps. See `src/web/admin/CLAUDE.md`.
